import os.path

import cv2
from moviepy.video.io.VideoFileClip import VideoFileClip


def is_file_a_video(file_name):
    # list of supporting file extensions
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.mpeg', '.mpg', '.3gp', '.3g2', '.webm']

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


if __name__ == "__main__":
    video_file = "C:\\Users\\Oleksander\\Videos\\20240407_120610A.MP4"
    image_file = "C:\\Users\\Oleksander\\Alex\\Projects\\family_album\\tests\\data\\images\\test_photo3.jpg"
    if os.path.exists(video_file):
        print(f'file {video_file} is video file = {is_file_a_video(video_file)}')
    else:
        print(f"File {video_file} does not exist!")

    if os.path.exists(image_file):
        print(f'file {image_file} is video file = {is_file_a_video(image_file)}')
    else:
        print(f"File {image_file} does not exist!")
