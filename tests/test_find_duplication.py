import asyncio
import os.path
import unittest

from src.family_album.utility_functions.find_duplicate_files import find_duplicate_files
from src.family_album.utility_functions.find_duplicate_files_async import find_duplicate_files_async
from src.family_album.utility_functions.find_duplicate_files_multythreaded import find_duplicate_files_multithreaded


class TestImageUtils(unittest.TestCase):

    def setUp(self):
        self._data_path = os.path.abspath('./data/duplication_check/')
        self._expected_duplications = {
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_16 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_16.jpg'],
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_21 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_21.jpg'],
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_3 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_3.jpg'],
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_33 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_33.jpg'],
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_37 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_37.jpg'],
            'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_44 - Copy.jpg': [
                'D:\\Shevchenko\\PetProjects\\family_album\\tests\\data\\duplication_check\\test_image_44.jpg']}

    def test_find_duplicate_files(self):
        result = find_duplicate_files(self._data_path)
        duplications = {file[0]: file[1:] for _, file in result.items()
                        if len(file) > 1}
        self.assertEqual(len(duplications.keys()), len(self._expected_duplications.keys()))
        self.assertEqual(len(duplications.values()), len(self._expected_duplications.values()))
        self.assertDictEqual(duplications, self._expected_duplications)

    def test_find_duplicate_files_async(self):
        result = asyncio.run(find_duplicate_files_async(self._data_path))
        duplications = {file[0]: file[1:] for _, file in result.items()
                        if len(file) > 1}
        self.assertEqual(len(duplications.keys()), len(self._expected_duplications.keys()))
        self.assertEqual(len(duplications.values()), len(self._expected_duplications.values()))
        self.assertDictEqual(duplications, self._expected_duplications)

    def test_find_duplicate_files_multithreaded(self):
        result = find_duplicate_files_multithreaded(self._data_path)
        duplications = {file[0]: file[1:] for _, file in result.items()
                        if len(file) > 1}
        self.assertEqual(len(duplications.keys()), len(self._expected_duplications.keys()))
        self.assertEqual(len(duplications.values()), len(self._expected_duplications.values()))
        # multi-thread version may put any of the files to be key - original, or value - duplicate in the dict
        originals = list(self._expected_duplications.keys())
        duplicates = [item for sublist in self._expected_duplications.values() for item in sublist]
        for key, value in duplications.items():
            self.assertTrue(key in originals or key in duplicates)
            self.assertTrue(value[0] in originals or value[0] in duplicates)

