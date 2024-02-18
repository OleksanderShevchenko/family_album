import cv2


def is_file_a_video(file_name: str) -> bool:
    """
     This function checks if passed file is video file by means of python-opencv lib

     :param file_name: full (absolute) name of the file.
     :return: boolean flag - true if the file may assume as image, ot False otherwise.
     """
    try:
        cap = cv2.VideoCapture(file_name)
        if not cap.isOpened():
            return False
        else:
            return True
    except Exception:
        return False


def _get_video_metadata(file_name: str) -> dict:
    """
     This function try to get video metadata by means of python-opencv lib

     :param file_name: full (absolute) name of the file.
     :return: dictionary with metadata or empty dictionary
     """
    output = {}
    try:
        cap = cv2.VideoCapture(file_name)
        output['resolution'] = [cap.get(3), cap.get(4)]
        output['bitrate'] = cap.get(5)
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