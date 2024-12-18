import cv2
from src.utility_functions.is_file_video import is_file_a_video


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