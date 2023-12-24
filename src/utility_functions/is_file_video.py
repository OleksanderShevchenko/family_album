import cv2


def is_file_a_video(file_name):
    try:
        cap = cv2.VideoCapture(file_name)
        if not cap.isOpened():
            return False
        else:
            return True
    except Exception:
        return False


if __name__ == "__main__":
    file = "C:\\Users\\oshe04\\Videos\\videoplayback.mp4"
    print(f'file {file} is video file = {is_file_a_video(file)}')
