"""
Unit tests for the File Organizer Memento pattern (OrganizerMemento,
OrganizerSaveManager, resumable analysis, resumable organization, and GUI integration).
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from src.family_album.gui.widgets.file_organizer import FileOrganizer
from src.family_album_lib.file_organizer_engine import (
    FileOrganizerEngine,
    OrganizePlanItem,
    OrganizeStats,
)
from src.family_album_lib.organizer_db import OrganizerDatabase
from src.family_album_lib.organizer_memento import (
    OrganizerMemento,
    OrganizerSaveManager,
    OrganizerStatus,
)


class TestOrganizerMemento(unittest.TestCase):
    """Test suite verifying pause, save state, verification, and resume for File Organizer."""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="test_org_memento_")
        self.source_dir = os.path.join(self.temp_root, "photos_raw")
        self.target_dir = os.path.join(self.temp_root, "photos_raw_organized")
        self.saves_dir = os.path.join(self.temp_root, "saves")
        os.makedirs(self.source_dir, exist_ok=True)

        self.files = []
        for i in range(6):
            fpath = os.path.join(self.source_dir, f"IMG_2023051{i + 1}_12000{i}.jpg")
            with open(fpath, "wb") as f:
                f.write(f"photo_payload_{i}".encode("utf-8"))
            self.files.append(fpath)

        self.save_manager = OrganizerSaveManager(saves_dir=self.saves_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_memento_serialization_and_save_manager(self):
        """OrganizerMemento serializes to JSON via OrganizerSaveManager and reloads identically."""
        plan = FileOrganizerEngine.scan_and_plan(self.source_dir, self.target_dir, max_workers=4)
        plan[0].status = "organized"
        plan[1].status = "skipped"

        plan_map = {os.path.normpath(item.file_path): item.to_dict() for item in plan}
        stats = OrganizeStats(total_scanned=6, total_processed=2, copied=1, skipped=1)
        memento = OrganizerMemento(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            phase="organize",
            files_count=6,
            plan_items=plan_map,
            stats=stats.to_dict(),
        )

        self.assertEqual(memento.analyzed_count, 6)
        self.assertEqual(memento.organized_count, 2)
        self.assertEqual(memento.pending_count, 4)

        saved_path = self.save_manager.save_memento(memento)
        self.assertTrue(os.path.isfile(saved_path))
        self.assertTrue(self.save_manager.has_save(self.source_dir))

        loaded = self.save_manager.load_memento(self.source_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.phase, "organize")
        self.assertEqual(loaded.files_count, 6)
        self.assertEqual(loaded.organized_count, 2)
        self.assertEqual(loaded.pending_count, 4)
        self.assertEqual(loaded.stats["copied"], 1)

        self.save_manager.delete_save(self.source_dir)
        self.assertFalse(self.save_manager.has_save(self.source_dir))

    def test_verify_location_checks_pending_files_only(self):
        """verify_location passes when moved ('organized') files left source_dir, but fails if pending files disappear."""
        plan = FileOrganizerEngine.scan_and_plan(self.source_dir, self.target_dir, action_type="move", max_workers=4)
        # Simulate first file already moved out of source_dir
        os.remove(plan[0].file_path)
        plan[0].status = "organized"

        memento = OrganizerMemento(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="move",
            phase="organize",
            files_count=len(plan),
            plan_items={os.path.normpath(i.file_path): i.to_dict() for i in plan},
        )
        ok, _ = self.save_manager.verify_location(memento)
        self.assertTrue(ok)

        # Now delete a still-pending file -> verification must fail
        os.remove(plan[1].file_path)
        ok2, reason2 = self.save_manager.verify_location(memento)
        self.assertFalse(ok2)
        self.assertIn("pending file", reason2)

    def test_resumable_analysis_skips_already_analyzed_files(self):
        """Resuming scan_and_plan from saved existing_items only inspects remaining files and yields identical plan."""
        full_plan = FileOrganizerEngine.scan_and_plan(self.source_dir, self.target_dir, max_workers=4)
        self.assertEqual(len(full_plan), 6)

        # Simulate checkpoint saved after analyzing first 3 files
        partial_items = full_plan[:3]
        memento = OrganizerMemento(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            phase="analyze",
            files_count=6,
            plan_items={os.path.normpath(i.file_path): i.to_dict() for i in partial_items},
        )
        self.save_manager.save_memento(memento)

        # Reload checkpoint and resume analysis
        loaded = self.save_manager.load_memento(self.source_dir)
        existing_map = {
            os.path.normpath(k): OrganizePlanItem.from_dict(v)
            for k, v in loaded.plan_items.items()
        }

        original_inspect = FileOrganizerEngine._inspect_single_file
        inspected_paths = []

        def tracking_inspect(full_path, target_abs, action_type, prefer_filename=True):
            inspected_paths.append(os.path.normpath(full_path))
            return original_inspect(full_path, target_abs, action_type, prefer_filename)

        with patch.object(FileOrganizerEngine, "_inspect_single_file", side_effect=tracking_inspect):
            resumed_plan = FileOrganizerEngine.scan_and_plan(
                source_dir=self.source_dir,
                target_dir=self.target_dir,
                mode="new_organization",
                action_type="copy",
                max_workers=4,
                existing_items=existing_map,
            )

        # Only the 3 remaining files should have been inspected!
        self.assertEqual(len(inspected_paths), 3)
        self.assertEqual(len(resumed_plan), 6)
        self.assertEqual(
            {i.file_name for i in resumed_plan},
            {i.file_name for i in full_plan},
        )

    def test_resumable_organization_continues_from_checkpoint(self):
        """Pausing organization after 3 files, saving Memento, and resuming completes all 6 files cleanly."""
        plan = FileOrganizerEngine.scan_and_plan(self.source_dir, self.target_dir, action_type="copy", max_workers=4)

        # Session 1: organize only the first 3 files
        session1_stats = FileOrganizerEngine.execute_plan(
            plan=plan[:3],
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            max_workers=4,
        )
        self.assertEqual(session1_stats.copied, 3)

        # Save Memento containing all 6 items (3 organized + 3 pending) and session1_stats
        memento = OrganizerMemento(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            phase="organize",
            files_count=len(plan),
            plan_items={os.path.normpath(i.file_path): i.to_dict() for i in plan},
            stats=session1_stats.to_dict(),
        )
        self.save_manager.save_memento(memento)

        # Session 2: reload memento and resume execute_plan
        loaded = self.save_manager.load_memento(self.source_dir)
        resumed_plan = [OrganizePlanItem.from_dict(v) for v in loaded.plan_items.values()]
        initial_stats = OrganizeStats.from_dict(loaded.stats)

        final_stats = FileOrganizerEngine.execute_plan(
            plan=resumed_plan,
            target_dir=self.target_dir,
            mode=loaded.mode,
            action_type=loaded.action_type,
            max_workers=4,
            initial_stats=initial_stats,
        )

        self.assertEqual(final_stats.copied, 6)
        self.assertEqual(final_stats.total_processed, 6)
        self.assertEqual(final_stats.errors, 0)
        self.assertTrue(all(item.status == "organized" for item in resumed_plan))
        with OrganizerDatabase(self.target_dir) as db:
            self.assertEqual(db.count_organized_files(), 6)

    def test_widget_pause_save_and_detect_saved_state(self):
        """FileOrganizer widget enables Save State & Resume on pause and detects saved checkpoints on reopen."""
        widget1 = FileOrganizer(saves_dir=self.saves_dir)
        widget1.selected_path = self.source_dir

        self.assertFalse(widget1.pb_save_state.isEnabled())
        self.assertFalse(widget1.pb_resume.isEnabled())

        # Simulate pause after 2 files analyzed
        partial_plan = FileOrganizerEngine.scan_and_plan(self.source_dir, self.target_dir, max_workers=2)[:2]
        widget1._on_worker_paused("analyze", partial_plan, OrganizeStats(total_scanned=6), 6)

        self.assertEqual(widget1.status, OrganizerStatus.PAUSED)
        self.assertTrue(widget1.pb_save_state.isEnabled())
        self.assertTrue(widget1.pb_resume.isEnabled())

        # Save state to disk
        widget1.evt_save_state()
        self.assertTrue(self.save_manager.has_save(self.source_dir))

        # Reopen directory in a fresh widget -> detects saved state and enables Resume
        widget2 = FileOrganizer(saves_dir=self.saves_dir)
        widget2.selected_path = self.source_dir
        self.assertTrue(widget2.pb_resume.isEnabled())
        self.assertIn("Saved analysis state found", widget2.lbl_info.text())

        # Restoring memento populates plan table and sets PAUSED status
        loaded = self.save_manager.load_memento(self.source_dir)
        widget2.restore_memento(loaded)
        self.assertEqual(widget2.status, OrganizerStatus.PAUSED)
        self.assertEqual(len(widget2._current_plan), 2)
        self.assertEqual(widget2.tbl_file_data.model().rowCount(), 2)


if __name__ == "__main__":
    unittest.main()
