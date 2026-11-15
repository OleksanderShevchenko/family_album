"""
Video utility module for the Family Album application.

Provides functions to identify video files, extract video container metadata
(resolution, bitrate, duration, frame count, audio tracks), and extract
recorded creation timestamps using MoviePy and OpenCV.
"""

from datetime import datetime
import os.path

import cv2
from moviepy.video.io.VideoFileClip import VideoFileClip, AudioFileClip
import pandas as pd
from pandas._libs.missing import NAType

from src.family_album.utility_functions.file_utils import get_file_creation_date


def is_file_a_video(file_name: str) -> bool:
    """
    Determine whether a given file is a playable video file.

    Checks known video file extensions first and verifies stream readability
    via OpenCV VideoCapture. If extension check is inconclusive, attempts to inspect
    the file structure using MoviePy VideoFileClip.

    Args:
        file_name (str): Path or filename to test.

    Returns:
        bool: True if file is a valid video, False otherwise.
    """
    # list of supporting file extensions
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.mpeg', '.mpg', '.3gp', '.3g2', '.webm',
                        '.mts']

    # check extension
    if file_name.lower().endswith(tuple(video_extensions)):
        try:
            # try to open it in OpenCV as video
            cap = cv2.VideoCapture(file_name)
            if cap.isOpened():
                return True
            else:
                return False
        except Exception:
            return False

    # if extension is not fit - check by getting inner video data info
    else:
        try:
            clip = VideoFileClip(file_name)
            if clip.n_frames > 1:
                return True
            else:
                return False
        except Exception:
            return False


def get_video_metadata(file_name: str) -> dict:
    """
    Retrieve video metadata dictionary combining MoviePy and OpenCV inspections.

    Extracts resolution, bitrate, duration, aspect ratio, frame count, codec,
    and audio channel characteristics.

    Args:
        file_name (str): Absolute filesystem path to the video file.

    Returns:
        dict: Dictionary containing parsed video attributes or empty dict on failure.
    """
    output = {}
    try:
        output.update(_get_video_meta_data_from_moviepy(file_name))
    except Exception:
        try:
            output.update(_get_video_meta_data_from_cv2(file_name))
        except Exception:
            pass
    return output


def get_video_creation_date(file_name: str) -> datetime | NAType:
    """
    Extract the original creation date of a video from container metadata.

    Inspects MoviePy/FFmpeg container headers for 'creation_time' tags (common in QuickTime,
    MP4, and smartphone cameras). Falls back to filesystem creation date if container
    metadata is absent.

    Args:
        file_name (str): Absolute path to the video file.

    Returns:
        datetime | NAType: Parsed datetime object if found, or pandas.NaT otherwise.
    """
    output = pd.NaT
    if not os.path.isfile(file_name):
        return output

    metadata = get_video_metadata(file_name)
    if metadata and 'infos' in metadata.keys():
        infos = metadata['infos']
        if infos and 'metadata' in infos.keys():
            meta_data = infos['metadata']
            if meta_data and 'creation_time' in meta_data.keys():
                date_time_str = str(meta_data['creation_time']).strip()
                clean_str = date_time_str.split('.')[0].rstrip('Z')
                for fmt in (
                    '%Y-%m-%d %H:%M:%S',
                    '%Y:%m:%d %H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%d  %H:%M:%S',
                    '%Y-%m-%d',
                ):
                    try:
                        parsed = datetime.strptime(clean_str, fmt)
                        if parsed.year >= 1980:
                            output = parsed
                            break
                    except ValueError:
                        output = pd.NaT
    if output is pd.NaT:
        output = get_file_creation_date(file_name)
    return output


def _get_video_meta_data_from_cv2(file_name: str) -> dict:
    """
    Extract video properties using OpenCV VideoCapture.

    Args:
        file_name (str): Path to the video file.

    Returns:
        dict: Extracted metrics including resolution, bitrate, codec, frame count, duration.
    """
    output = {}
    if is_file_a_video(file_name):
        cap = cv2.VideoCapture(file_name)
        output['resolution'] = [cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)]
        output['bitrate'] = int(cap.get(cv2.CAP_PROP_FPS))
        output['codec'] = cap.get(cv2.CAP_PROP_FOURCC)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        output['n_frames'] = frame_count
        output['duration'] = frame_count / output['bitrate']
    return output


def _get_video_meta_data_from_moviepy(file_name: str) -> dict:
    """
    Extract video properties using MoviePy VideoFileClip.

    Args:
        file_name (str): Path to the video file.

    Returns:
        dict: Detailed metadata including container infos, dimensions, bitrate, audio track details.
    """
    output = {}
    if is_file_a_video(file_name):
        clip = VideoFileClip(file_name)
        output['resolution'] = [clip.w, clip.h]
        output['bitrate'] = int(clip.fps)
        output['duration'] = float(clip.duration)
        output['aspect_ratio'] = clip.aspect_ratio
        output['n_frames_moviepy'] = int(clip.n_frames)
        output['infos'] = clip.reader.infos
        audio: AudioFileClip = clip.audio
        if audio is not None:
            output['audio_duration'] = f"{audio.duration}"
            output['audio_bitrate'] = f"{audio.reader.bitrate}"
            output['audio_codec'] = f"{audio.reader.codec}"
        else:
            output['audio_moviepy'] = "No audio"
    return output


def _open_video(file_name: str) -> None:
    """
    Debug playback utility displaying video frames in an OpenCV GUI window.

    Args:
        file_name (str): Path to video file.
    """
    cap = cv2.VideoCapture(file_name)

    if not cap.isOpened():
        print(f"Cannot open {file_name}")
        exit()

    while cap.isOpened():

        ret, frame = cap.read()

        # if frame is read correctly ret is True
        if not ret:
            print("Stream stopped.")
            break

        cv2.imshow('Video', frame)

        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

