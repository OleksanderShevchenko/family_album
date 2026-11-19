"""
Video utility module for the Family Album application.

Provides functions to identify video files (including animated GIFs),
quickly read video resolution via OpenCV/Pillow, and extract container
metadata (resolution, bitrate, duration, frame count, audio tracks, creation_time)
using MoviePy and OpenCV.
"""

import os.path

import cv2
from moviepy.video.io.VideoFileClip import VideoFileClip, AudioFileClip
from PIL import Image

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
