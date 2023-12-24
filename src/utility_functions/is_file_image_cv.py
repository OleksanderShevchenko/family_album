import cv2

def is_image_file(filename):
    try:
        img = cv2.imread(filename)
        if img is not None:
            return True
        else:
            return False
    except:
        return False