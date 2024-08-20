from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, send_file; 
import geopandas as gpd
from shapely.geometry import Point
import requests
import pandas as pd
from rtree import index as index_func
import os
import json
import shutil
from werkzeug.utils import secure_filename
import zipfile
from datetime import datetime 
import subprocess
import numpy as np
import matplotlib.pyplot as plt



def sum_first_column(file_path):
    df = pd.read_excel(file_path)
    return df.iloc[:, 0].sum()

def create_initial_process(file_path):
    # file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'process.json')
    
    data = [
        {
            "Site": "Mid",
            "Process": "Slack powerplant",
            "inst-cap": 0,
            "cap-lo": 0,
            "cap-up": float('inf'),
            "max-grad": float('inf'),  # Using float('inf') for Infinity
            "min-fraction": 0.0,
            "inv-cost": 999999999999,
            "fix-cost": 999999999999,
            "var-cost": 999999999999,
            "wacc": 0.07,
            "depreciation": 1,
            "area-per-cap": float('nan'),  # Using float('nan') for NaN
            "support_timeframe": 2020
        },
        {
            "Site": "Mid",
            "Process": "Slack neg",
            "inst-cap": 0,
            "cap-lo": 0,
            "cap-up": float('inf'),
            "max-grad": float('inf'),  # Using float('inf') for Infinity
            "min-fraction": 0.0,
            "inv-cost": 0,
            "fix-cost": 0,
            "var-cost": 0,
            "wacc": 0.07,
            "depreciation": 1,
            "area-per-cap": float('nan'),
            "support_timeframe": 2020
        }
    ]

    # Write the data to the JSON file with indentation for readability
    with open(file_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)  # 4 spaces for indentation



def transform_data(input_directory, output_directory):
    try:
        # Paths to the JSON files
        wind_data_path = os.path.join(input_directory, 'wind_data.json')
        pv_data_path = os.path.join(input_directory, 'pv_data.json')
        avg_q_path = os.path.join(input_directory, 'avg_q.json')

        # Read wind data
        with open(wind_data_path, 'r') as f:
            wind_data = json.load(f)

        # Read pv data
        with open(pv_data_path, 'r') as f:
            pv_data = json.load(f)

        # Read avg_q data and parse discharge_timeseries
        with open(avg_q_path, 'r') as f:
            avg_q_data = json.load(f)
            discharge_timeseries_json = json.loads(avg_q_data['discharge_timeseries'])
            discharge_timeseries = pd.DataFrame(discharge_timeseries_json['data'],
                                                 columns=discharge_timeseries_json['columns'],
                                                 index=discharge_timeseries_json['index'])

        transformed_data = []

        # Assuming wind_data and pv_data have the same timestamps and lengths
        for i in range(len(wind_data)):
            timestamp = list(wind_data.keys())[i]
            wind_electricity = wind_data[timestamp]['electricity']
            pv_electricity = pv_data[timestamp]['electricity']
            
            # Get the corresponding discharge value for the current index
            hydro_value = discharge_timeseries.iloc[i]['discharge']
            max_hydro = max(discharge_timeseries['discharge'])
            if hydro_value != 0:
                hydro_value = hydro_value / max_hydro * 0.2

            entry = {
                "support_timeframe": 2020,
                "t": i,
                "Mid": {
                    "Wind": wind_electricity,
                    "Solar": pv_electricity,
                    "Hydro": hydro_value
                }
            }
            transformed_data.append(entry)

        # Write transformed data to new JSON file
        output_path = os.path.join(output_directory, 'supim.json')

        with open(output_path, 'w') as f:
            json.dump(transformed_data, f, indent=4)

        print(f"Transformation complete. File saved as {output_path}.")

    except Exception as e:
        print(f"An error occurred: {e}")


def move_files(source_dir, destination_dir):

    try:
        # Source file paths
        source_process = os.path.join(source_dir, 'process.json')

        
        # Destination file paths
        dest_process = os.path.join(destination_dir, 'process1.json')

        
        # Move files
        shutil.move(source_process, dest_process)

        
        print(f"Files moved successfully from {source_dir} to {destination_dir}")
        return True
    
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False
    


# Function to clear results folder
def clear_results_folder(RESULTS_FOLDER):
    print(f"Clearing results folder: {RESULTS_FOLDER}")
    for filename in os.listdir(RESULTS_FOLDER):
        file_path = os.path.join(RESULTS_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

# Function to clear result text files
def clear_result_txt(WORKING_DIR):
    print(f"Clearing result text files in: {WORKING_DIR}")
    try:
        for filename in os.listdir(WORKING_DIR):
            if 'resultsingle-year' in filename and filename.endswith('.log'):
                file_path = os.path.join(WORKING_DIR, filename)
                os.remove(file_path)
                print(f'Deleted: {file_path}')
    except Exception as e:
        print(f'Failed to clear result text files. Reason: {e}')

# Function to move result PNG files
def move_result_png_file(RESULTS_FOLDER, scripts_dir):
    source_folder = os.path.join(RESULTS_FOLDER)
    target_folder = os.path.join(scripts_dir, 'static', 'images')

    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
        print(f'Created target directory: {target_folder}')

    for root, dirs, files in os.walk(source_folder):
        for file in files:
            if file.endswith('.png') and 'Mid' in file:
                source_file_path = os.path.join(root, file)
                target_file_path = os.path.join(target_folder, file)
                try:
                    shutil.copy(source_file_path, target_file_path)
                    print(f'Copied: {source_file_path} to {target_file_path}')
                except Exception as e:
                    print(f'Failed to copy {source_file_path}. Reason: {e}')


def create_zip_of_results(RESULTS_FOLDER):
    zip_filename = os.path.join(RESULTS_FOLDER, 'results.zip')
    print(f"Creating zip file: {zip_filename}")
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(RESULTS_FOLDER):
                for file in files:
                    if file != 'results.zip':
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, RESULTS_FOLDER))
    except Exception as e:
        print(f"Failed to create zip file: {str(e)}")
        raise RuntimeError(f"Failed to create zip file: {str(e)}")
    return zip_filename



#