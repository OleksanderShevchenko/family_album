from PIL import Image


def is_file_a_picture(file_name):
    try:
        img = Image.open(file_name)
        img.verify()  # перевірка на коректність зображення
        return True
    except:
        return False