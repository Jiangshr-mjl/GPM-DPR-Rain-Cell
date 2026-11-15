"""独立合成数据测试；不读取真实观测数据，也不访问网络。"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np
import xarray as xr

from gpm_raincell.identify import connect_time, identify_rc, region_mask
from gpm_raincell.batch import build_dataset, main, process_file


class IdentifyTests(unittest.TestCase):
    def test_threshold_diagonal_and_minimum_size(self):
        rain = np.zeros((6, 8), dtype=np.float32)
        rain[0, 0] = rain[1, 1] = rain[2, 2] = rain[3, 3] = 0.5
        rain[0, 6:8] = 1
        rain[1, 7] = 1  # 三像元，应该剔除
        rain[5, 0:4] = 2
        expected = np.zeros(rain.shape, dtype=np.int32)
        expected[[0, 1, 2, 3], [0, 1, 2, 3]] = 1
        expected[5, 0:4] = 2
        original = rain.copy()
        np.testing.assert_array_equal(identify_rc(rain), expected)
        np.testing.assert_array_equal(rain, original)

    def test_nonfinite_empty_and_custom_options(self):
        rain = np.array([[np.nan, np.inf, -np.inf, -9999, 0.49, 0.5]])
        np.testing.assert_array_equal(identify_rc(rain), np.zeros((1, 6)))
        expected = np.array([[0, 0, 0, 0, 0, 1]])
        np.testing.assert_array_equal(identify_rc(rain, min_pixels=1), expected)
        self.assertEqual(identify_rc(np.empty((0, 5))).shape, (0, 5))
        self.assertFalse(identify_rc(np.ones((2, 2)), threshold=2).any())

    def test_legacy_output_array(self):
        rain = np.ones((2, 2), dtype=np.float32)
        labels = np.full_like(rain, 8)
        self.assertIs(identify_rc(rain, labels), labels)
        np.testing.assert_array_equal(labels, np.ones((2, 2)))
        identify_rc(np.zeros((2, 2)), labels)
        self.assertFalse(labels.any())

    def test_invalid_arguments(self):
        for options in ({"threshold": -1}, {"threshold": np.nan},
                        {"min_pixels": 0}, {"min_pixels": 1.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                identify_rc(np.ones((2, 2)), **options)
        with self.assertRaises(ValueError):
            identify_rc(np.ones(4))
        with self.assertRaises(ValueError):
            identify_rc(np.ones((2, 2)), np.zeros((1, 1)))
        rain = np.ones((2, 2))
        with self.assertRaises(ValueError):
            identify_rc(rain, rain)

    def test_region_middle_beam_and_boundaries(self):
        lat = np.array([[50, -5, 50], [20, 35, 20], [20, 36, 20]])
        lon = np.array([[0, 95, 0], [120, 145, 120], [120, 120, 120]])
        np.testing.assert_array_equal(region_mask(lat, lon), [True, True, False])
        pixels = region_mask(lat, lon, mid=False)
        self.assertEqual(pixels.shape, lat.shape)
        self.assertFalse(pixels[0, 0])
        self.assertTrue(pixels[2, 0])
        with self.assertRaises(ValueError):
            region_mask(lat, lon, extents=(145, 95, -5, 35))


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "input" / "2020" / "001" / "granule.HDF5"
        self.source.parent.mkdir(parents=True)
        self.destination = self.root / "output" / "granule.HDF5.nc"
        self.make_granule(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def make_granule(path):
        shape = (8, 5)
        rain = np.zeros(shape, dtype=np.float32)
        rain[0:2, 0:2] = 0.5
        rain[4:6, 3:5] = 1
        rain[7, 0] = 0.7
        with h5py.File(path, "w") as handle:
            handle["FS/Latitude"] = np.full(shape, 20.0, dtype=np.float32)
            handle["FS/Longitude"] = np.full(shape, 120.0, dtype=np.float32)
            handle["FS/SLV/precipRateNearSurface"] = rain
            handle["FS/PRE/heightStormTop"] = np.full(shape, 5000.0)
            handle["FS/CSF/typePrecip"] = np.full(shape, 10000000, dtype=np.int32)
            handle["FS/SLV/precipRate"] = np.ones((*shape, 3), dtype=np.float32)
            handle["FS/SLV/zFactorFinal"] = np.ones((*shape, 3, 2), dtype=np.float32)
            handle["FS/SLV/paramDSD"] = np.ones((*shape, 3, 2), dtype=np.float32)
            for name, value in (("Year", 2020), ("Month", 1), ("DayOfMonth", 1), ("Hour", 3)):
                handle[f"FS/ScanTime/{name}"] = np.full(shape[0], value, dtype=np.int32)

    def test_time_and_dataset(self):
        with h5py.File(self.source, "r") as handle:
            times = connect_time(handle)
        self.assertEqual(times.dtype, np.dtype("datetime64[h]"))
        self.assertEqual(times[0], np.datetime64("2020-01-01T03"))
        with build_dataset(self.source) as ds:
            self.assertEqual(dict(ds.sizes), dict(nscan=8, nray=5, nbin=3, nfreq=2, nDSD=2))
            self.assertEqual(ds.pr3d.dims, ("nscan", "nray", "nbin"))
            self.assertEqual(ds.R.dims, ("nscan", "nray", "nbin", "nfreq"))
            self.assertEqual(float(ds.rcid.max()), 2)
            self.assertTrue(np.isnan(ds.rcid.values[7, 0]))
            self.assertTrue(np.isnan(ds.prs.values[3, 0]))
            self.assertEqual(ds.attrs["source_file"], self.source.name)

    def test_no_false_connection_across_removed_scans(self):
        with h5py.File(self.source, "r+") as handle:
            handle["FS/Latitude"][2:4] = 50
            rain = np.zeros((8, 5), dtype=np.float32)
            rain[0:2, 0:2] = 1
            rain[4:6, 0:2] = 1
            handle["FS/SLV/precipRateNearSurface"][:] = rain
            handle["FS/SLV/precipRate"][:] = np.broadcast_to(
                np.arange(8)[:, None, None], (8, 5, 3)
            )
        with build_dataset(self.source) as ds:
            self.assertEqual(ds.sizes["nscan"], 6)
            self.assertEqual(ds.rcid.values[1, 0], 1)
            self.assertEqual(ds.rcid.values[2, 0], 2)
            np.testing.assert_array_equal(ds.scan_index.values, [0, 1, 4, 5, 6, 7])
            np.testing.assert_array_equal(ds.pr3d.values[:, 0, 0], ds.scan_index.values)

    def test_write_skip_and_overwrite(self):
        self.assertEqual(process_file(self.source, self.destination), "written")
        with xr.open_dataset(self.destination) as ds:
            self.assertEqual(float(ds.rcid.max()), 2)
            self.assertEqual(ds.attrs["connectivity"], 8)
            self.assertEqual(ds.sizes["nbin"], 3)  # 不再硬编码 176
        before = self.destination.read_bytes()
        self.assertEqual(process_file(self.source, self.destination, threshold=2), "existing")
        self.assertEqual(self.destination.read_bytes(), before)
        self.assertEqual(process_file(self.source, self.destination, overwrite=True, min_pixels=1), "written")
        with xr.open_dataset(self.destination) as ds:
            self.assertEqual(float(ds.rcid.max()), 3)

    def test_empty_or_outside_region(self):
        self.assertIsNone(build_dataset(self.source, extents=(0, 10, 0, 10)))
        self.assertEqual(process_file(self.source, self.destination, threshold=2), "empty")
        self.assertFalse(self.destination.exists())

    def test_rejects_input_as_output(self):
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            process_file(self.source, self.source, overwrite=True)
        self.assertEqual(self.source.read_bytes(), before)

    def test_existing_result_is_kept_when_recompute_is_empty(self):
        self.assertEqual(process_file(self.source, self.destination), "written")
        before = self.destination.read_bytes()
        self.assertEqual(process_file(self.source, self.destination,
                                      overwrite=True, threshold=2), "empty")
        self.assertEqual(self.destination.read_bytes(), before)

    def test_failed_write_preserves_old_output_and_cleans_temporary(self):
        self.destination.parent.mkdir()
        self.destination.write_bytes(b"existing result")
        with patch.object(xr.Dataset, "to_netcdf", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                process_file(self.source, self.destination, overwrite=True)
        self.assertEqual(self.destination.read_bytes(), b"existing result")
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_recursive_batch_continues_after_bad_file(self):
        (self.source.parent / "broken.h5").write_bytes(b"not HDF5")
        (self.source.parent / "ignore.txt").write_text("ignored", encoding="utf-8")
        output = self.root / "batch-output"
        with self.assertLogs("gpm_raincell.batch", level="INFO"):
            code = main(["--input", str(self.root / "input"), "--output", str(output)])
        self.assertEqual(code, 1)
        result = output / "2020" / "001" / "granule.HDF5.nc"
        self.assertTrue(result.is_file())
        self.assertFalse((output / "2020" / "001" / "broken.h5.nc").exists())

    def test_missing_required_field(self):
        with h5py.File(self.source, "r+") as handle:
            del handle["FS/SLV/paramDSD"]
        with self.assertRaises(KeyError):
            build_dataset(self.source)
        self.assertFalse(self.destination.exists())

    def test_cli_and_legacy_entry_points(self):
        project = Path(__file__).resolve().parents[1]
        # 在项目外运行旧入口，检查无需手工设置 PYTHONPATH。
        for filename in ("DPR_baidrc.py", "DPRtoRCmultiyears.py"):
            result = subprocess.run(
                [sys.executable, str(project / filename), "--help"],
                cwd=self.root, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"--threshold", result.stdout)
        result = subprocess.run(
            [sys.executable, "-m", "gpm_raincell", "--input", str(self.source),
             "--output", str(self.destination.parent)],
            cwd=project, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.destination.is_file())

    def test_invalid_cli_arguments(self):
        with patch("sys.stderr"):
            for extra in (["--min-pixels", "0"], ["--threshold", "nan"],
                          ["--extent", "145", "95", "-5", "35"]):
                with self.subTest(extra=extra), self.assertRaises(SystemExit) as context:
                    main(["--input", str(self.source), "--output", str(self.root / "output"), *extra])
                self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
