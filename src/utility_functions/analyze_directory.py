import os

import pandas as pd

from src.utility_functions.file_utils import get_file_size, get_file_creation_date
from src.utility_functions.image_utils import is_image_file, get_image_creation_date, get_image_size, get_image_maker
from src.utility_functions.video_utils import is_file_a_video, get_video_metadata

_TEMPLATE = {"file_name": "str", "file_path": "str", "file_date_created": "datetime64[s]",
             "image_date_take": "datetime64[s]", "file_size": "int64", "is_image": "bool", "is_video": "bool",
             "image_size": "str", "image_maker": "str", "video_resolution": "str", "video_bitrate": "int64",
             "video_duration": "int64", "video_codec": "str"}


def analyze_directory(directory: str) -> pd.DataFrame:
    output: pd.DataFrame = _create_empty_dataframe(_TEMPLATE)
    if not os.path.isdir(directory):
        return output

    for root, dirs, files in os.walk(directory):
        for filename in files:
            full_file_name = os.path.join(root, filename)
            row_data = {"file_name": filename, "file_path": full_file_name, "file_size": get_file_size(full_file_name),
                        "file_date_created": get_file_creation_date(full_file_name)}
            is_image = is_image_file(full_file_name)
            row_data["is_image"] = is_image
            is_video = is_file_a_video(full_file_name)
            row_data["is_video"] = is_video
            if is_image:
                image_date_taken = get_image_creation_date(full_file_name)
                image_size = get_image_size(full_file_name)
                image_maker = get_image_maker(full_file_name)
                row_data["image_size"] = f'{image_size[0]}x{image_size[1]}'
                row_data["image_date_take"] = image_date_taken
                row_data["image_maker"] = image_maker
            else:
                row_data["image_size"] = ''
                row_data["image_date_take"] = pd.NaT
                row_data["image_maker"] = ""
            if is_video:
                meta_data = get_video_metadata(full_file_name)
                row_data["video_resolution"] = f'{meta_data["resolution"][0]}x{meta_data["resolution"][1]}'
                row_data["video_bitrate"] = meta_data['bitrate']
                row_data["video_duration"] = meta_data['duration']
                row_data["video_codec"] = meta_data['codec']
            else:
                row_data["video_resolution"] = ''
                row_data["video_bitrate"] = 0
                row_data["video_duration"] = 0
                row_data["video_codec"] = ''
            temp_output = _fill_dataframe_row(output, row_data)
            if temp_output is not None:
                output = temp_output
            else:
                print(f'File {full_file_name} was skipped in analyses due to error!')
    return output


def _create_empty_dataframe(columns_dict: dict) -> pd.DataFrame:
    """
    Create an empty pandas DataFrame with specified columns.
    Parameters:
    columns_dict (dict): A dictionary where keys are column names and values are column types.
    Returns:
    pd.DataFrame: An empty DataFrame with specified columns.
    """
    # Create an empty DataFrame
    df = pd.DataFrame()
    # Add columns to DataFrame based on the input dictionary
    for column_name, column_type in columns_dict.items():
        df[column_name] = pd.Series(dtype=column_type)
    return df


def _fill_dataframe_row(df: pd.DataFrame, row_data: dict) -> pd.DataFrame | None:
    """
    Fill a DataFrame with row data if column names and data types match.
    Parameters:
    df (pd.DataFrame): DataFrame to fill.
    row_data (dict): A dictionary where keys are column names and values are row data.
    Returns:
    pd.DataFrame: Updated DataFrame if successful, otherwise returns None.
    """
    # Check if column names match
    if not set(row_data.keys()) == set(df.columns):
        print("Column names in row_data do not match DataFrame columns.")
        return None
    try:
        # Inserting the new row
        df.loc[len(df)] = row_data
        # Reset the index
        df = df.reset_index(drop=True)
        return df
    except Exception as err:
        print(f'Error occur: {err}')
        return None
