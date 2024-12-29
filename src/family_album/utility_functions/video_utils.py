import os.path

import cv2
from moviepy.video.io.VideoFileClip import VideoFileClip


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
        cap = cv2.VideoCapture(file_name)
        output['resolution'] = [cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)]
        output['bitrate'] = int(cap.get(cv2.CAP_PROP_FPS))
        output['codec'] = cap.get(cv2.CAP_PROP_FOURCC)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        output['duration'] = frame_count / output['bitrate']
    except Exception:
        pass
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