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
from PIL import Image

from src.family_album.utility_functions.file_utils import get_file_creation_date

VIDEO_EXTENSIONS = (
    '.mp4', '.m4v', '.avi', '.mov', '.mkv', '.wmv', '.flv',
    '.mpeg', '.mpg', '.3gp', '.3g2', '.webm', '.mts', '.m2ts',
    '.ts', '.vob', '.ogv',
)


def has_video_extension(file_name: str) -> bool:
    """
    Fast check whether a filename has a recognized video extension.

    Args:
        file_name (str): Path or filename to inspect.

    Returns:
        bool: True if the file extension matches a known video container format.
    """
    return bool(file_name and file_name.lower().endswith(VIDEO_EXTENSIONS))


def _is_animated_gif(file_name: str) -> bool:
    """
    Fast check using Pillow whether a `.gif` file is animated (more than 1 frame),
    without launching MoviePy/FFmpeg.

    Args:
        file_name (str): Path to a `.gif` file.

    Returns:
        bool: True if the GIF contains multiple frames, False otherwise.
    """
    try:
        with Image.open(file_name) as img:
            return bool(getattr(img, "is_animated", False) or getattr(img, "n_frames", 1) > 1)
    except Exception:
        return False


def is_file_a_video(file_name: str) -> bool:
    """
    Determine whether a given file is a playable video file (or animated GIF).

    Checks known video file extensions first and immediately returns False for
    non-video extensions (avoiding spawning external FFmpeg/MoviePy processes on
    photos or other files). Animated GIFs are checked via Pillow (`is_animated`).
    For matching video extensions, verifies stream readability via OpenCV
    VideoCapture and releases the handle in a finally block.

    Args:
        file_name (str): Path or filename to test.

    Returns:
        bool: True if file is a valid video (or animated GIF), False otherwise.
    """
    if not file_name or not os.path.isfile(file_name):
        return False

    lower_name = file_name.lower()
    if lower_name.endswith('.gif'):
        return _is_animated_gif(file_name)

    if not has_video_extension(file_name):
        return False

    cap = None
    try:
        cap = cv2.VideoCapture(file_name)
        return bool(cap.isOpened())
    except Exception:
        return False
    finally:
        if cap is not None:
            cap.release()


def get_video_resolution_fast(file_name: str) -> str:
    """
    Quickly retrieve video frame resolution ('WIDTHxHEIGHT') using OpenCV (or Pillow
    for animated GIFs) without spawning an external FFmpeg subprocess via MoviePy.

    Args:
        file_name (str): Path to the video file.

    Returns:
        str: Resolution string (e.g. '1920x1080'), or empty string if unavailable.
    """
    if not file_name or not os.path.isfile(file_name):
        return ""

    if file_name.lower().endswith('.gif'):
        try:
            with Image.open(file_name) as img:
                if getattr(img, "is_animated", False) or getattr(img, "n_frames", 1) > 1:
                    w, h = img.size
                    if w > 0 and h > 0:
                        return f"{w}x{h}"
        except Exception:
            pass
        return ""

    if not has_video_extension(file_name):
        return ""

    cap = None
    try:
        cap = cv2.VideoCapture(file_name)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                return f"{w}x{h}"
    except Exception:
        pass
    finally:
        if cap is not None:
            cap.release()
    return ""


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
    if not file_name or not os.path.isfile(file_name):
        return output
    if not has_video_extension(file_name) and not file_name.lower().endswith('.gif'):
        return output
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
        cap = None
        try:
            cap = cv2.VideoCapture(file_name)
            output['resolution'] = [cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)]
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            output['bitrate'] = fps
            output['codec'] = cap.get(cv2.CAP_PROP_FOURCC)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            output['n_frames'] = frame_count
            output['duration'] = frame_count / fps if fps > 0 else 0
        finally:
            if cap is not None:
                cap.release()
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
        clip = None
        try:
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
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass
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
