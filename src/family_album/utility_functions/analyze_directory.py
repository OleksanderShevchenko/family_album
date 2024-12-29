import os

import pandas as pd

from src.family_album.utility_functions.file_utils import get_file_size, get_file_creation_date
from src.family_album.utility_functions.image_utils import (is_image_file, get_image_creation_date, get_image_size,
                                                            get_image_maker)
from src.family_album.utility_functions.video_utils import is_file_a_video, get_video_metadata, get_video_creation_date


_TEMPLATE = {"file_name": "str", "file_path": "str", "file_date_created": "datetime64[s]",
             "date_take": "datetime64[s]", "file_size": "int64", "is_image": "bool", "is_video": "bool",
             "resolution": "str", "maker": "str", "video_bitrate": "int64",
             "video_duration": "int64"}


def analyze_directory(directory: str) -> pd.DataFrame:
    output: pd.DataFrame = _create_empty_dataframe(_TEMPLATE)
    if not os.path.isdir(directory):
        return output

    for root, dirs, files in os.walk(directory):
        for filename in files:
            full_file_name = os.path.join(root, filename)
            row_data = {"file_name": filename, "file_path": full_file_name, "file_size": get_file_size(full_file_name),
                        "file_date_created": get_file_creation_date(full_file_name), "video_bitrate": 0,
                        "video_duration": 0}
            is_video = is_file_a_video(full_file_name)
            row_data["is_video"] = is_video
            if is_video:  # avoid is_video = True and is_image = True (for gif)
                is_image = False
            else:
                is_image = is_image_file(full_file_name)
            row_data["is_image"] = is_image
            if is_video:
                date_taken = get_video_creation_date(full_file_name)
                meta_data = get_video_metadata(full_file_name)
                maker = "Unknown"

                row_data["date_take"] = date_taken
                row_data["maker"] = maker
                if meta_data:
                    row_data["resolution"] = f'{meta_data["resolution"]}'
                    row_data["video_bitrate"] = meta_data['bitrate']
                    row_data["video_duration"] = meta_data['duration']
            elif is_image:
                date_taken = get_image_creation_date(full_file_name)
                image_size = get_image_size(full_file_name)
                maker = get_image_maker(full_file_name)
                row_data["resolution"] = f'{image_size[0]}x{image_size[1]}'
                row_data["date_take"] = date_taken
                row_data["maker"] = maker
            else:
                row_data["resolution"] = ''
                row_data["date_take"] = get_file_creation_date(full_file_name)
                row_data["maker"] = ""

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
