import os.path

import cv2
from moviepy.video.io.VideoFileClip import VideoFileClip, AudioFileClip


def is_file_a_video(file_name):
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
        except (IOError, OSError):
            return False


def get_video_metadata(file_name: str) -> dict:
    """
     This function try to get video metadata by means of python-opencv lib

     :param file_name: full (absolute) name of the file.
     :return: dictionary with metadata or empty dictionary
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


def _get_video_meta_data_from_cv2(file_name: str) -> dict:
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

