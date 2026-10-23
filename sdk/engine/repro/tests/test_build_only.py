"""Build-tool tests only: no engine, host admission, saved-block execution or network."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import sys
import subprocess


SCRIPT = Path(__file__).resolve().parents[1] / "build_pair03.py"
spec = importlib.util.spec_from_file_location("build_pair03", SCRIPT)
build = None
if SCRIPT.exists():
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)


class BuildOnlyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build, "The build-only bootstrap is not implemented yet")
        self.temp = tempfile.TemporaryDirectory(prefix="pair03-build-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def archive(self, members):
        path = self.root / "source.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, content, link in members:
                info = tarfile.TarInfo(name)
                if link is not None:
                    info.type = tarfile.SYMTYPE
                    info.linkname = link
                    archive.addfile(info)
                else:
                    info.size = len(content)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(content))
        return path

    # Dropping checksum validation must not allow a corrupted cached download.
    def test_corrupt_archive_is_rejected_before_extraction(self):
        path = self.root / "cache.tar.gz"
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            build.verify_download(path, {"sha256": "0" * 64, "bytes": 7})

    def test_truncated_download_is_rejected(self):
        path = self.root / "cache.tar.gz"
        path.write_bytes(b"abc")
        with self.assertRaisesRegex(ValueError, "SIZE"):
            build.verify_download(path, {
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "bytes": 4,
            })

    # Unsafe archives must leave both their destination and outside paths untouched.
    def test_parent_traversal_leaves_no_extracted_files(self):
        archive = self.archive([("top/../../escape", b"bad", None)])
        dest = self.root / "destination"
        with self.assertRaises(ValueError):
            build.extract_archive(archive, dest)
        self.assertFalse(dest.exists())
        self.assertFalse((self.root / "escape").exists())

    def test_external_symlink_is_rejected(self):
        archive = self.archive([("top/link", b"", "../../escape")])
        dest = self.root / "destination"
        with self.assertRaises(ValueError):
            build.extract_archive(archive, dest)
        self.assertFalse(dest.exists())

    def test_symlink_cannot_escape_after_archive_top_directory_is_removed(self):
        (self.root / "external").write_bytes(b"private outside file")
        archive = self.archive([("top/link", b"", "../external")])
        dest = self.root / "destination"
        with self.assertRaises(ValueError):
            build.extract_archive(archive, dest)
        self.assertFalse(dest.exists())
        self.assertEqual((self.root / "external").read_bytes(), b"private outside file")

    def test_internal_symlink_from_real_upstream_layout_is_preserved(self):
        archive = self.archive([
            ("top/tests/include/wasm.h", b"header", None),
            ("top/lib/wasm.h", b"", "../tests/include/wasm.h"),
        ])
        dest = self.root / "destination"
        build.extract_archive(archive, dest)
        self.assertEqual((dest / "lib/wasm.h").read_bytes(), b"header")

    def test_existing_source_directory_is_not_overwritten(self):
        archive = self.archive([("top/existing", b"new", None)])
        dest = self.root / "destination"
        dest.mkdir()
        (dest / "existing").write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            build.extract_archive(archive, dest)
        self.assertEqual((dest / "existing").read_bytes(), b"original")

    # An unhandled absolute replace would silently compile the old developer tree.
    def test_overlay_uses_relative_replacements_and_keeps_input_unchanged(self):
        original = ("module local/pair\n\ngo 1.25\n"
                    "replace github.com/ethereum/go-ethereum => /old/private/geth\n"
                    "replace github.com/offchainlabs/nitro => /old/private/nitro\n"
                    "replace local/rhook-robinhood => /old/private/native\n")
        result = build.module_overlay(original, {
            "github.com/ethereum/go-ethereum": "../../../nitro/go-ethereum",
            "github.com/offchainlabs/nitro": "../../../nitro",
            "local/rhook-robinhood": "../prestate",
        })
        self.assertNotIn("/old/private/", result)
        self.assertIn("local/rhook-robinhood => ../prestate", result)
        self.assertIn("/old/private/native", original)

    def test_unknown_absolute_replace_is_not_silently_retained(self):
        with self.assertRaisesRegex(ValueError, "UNRELOCATED"):
            build.module_overlay("module x\nreplace example.com/x => /old/x\n", {})

    # Ambient HOME/cache/workspace settings cannot enter any compiler subprocess.
    def test_compiler_environment_is_local_and_drops_credentials(self):
        env = build.build_environment(self.root, Path("/usr/local/bin"))
        self.assertEqual(env["HOME"], str(self.root / "home"))
        self.assertEqual(env["GOMODCACHE"], str(self.root / "cache/go-mod"))
        self.assertEqual(env["CARGO_HOME"], str(self.root / "cache/cargo"))
        self.assertEqual(env["GOWORK"], "off")
        self.assertEqual(env["GOENV"], "off")
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("ALCHEMY_API_KEY", env)
        self.assertNotIn("RUSTC_WRAPPER", env)
        self.assertEqual(env.get("npm_config_globalconfig"), str(self.root / "home/npm-global.rc"))
        self.assertEqual(env.get("npm_config_userconfig"), str(self.root / "home/npm-user.rc"))

    def test_cargo_config_in_an_external_ancestor_is_rejected(self):
        self.assertTrue(hasattr(build, "reject_ambient_configuration"), "Cargo ancestor config check absent")
        parent = self.root / "parent"
        (parent / ".cargo").mkdir(parents=True)
        (parent / ".cargo/config.toml").write_text('[build]\nrustflags = ["--cfg", "unexpected"]\n')
        work = parent / "work"
        work.mkdir()
        with self.assertRaisesRegex(ValueError, "AMBIENT_CARGO_CONFIG"):
            build.reject_ambient_configuration(work)

    # Deserializing or hashing a fixture must never invoke its execution engine.
    def test_fixture_is_explicit_and_verified_without_execution(self):
        path = self.root / "input.json"
        path.write_bytes(b"{}")
        build.verify_input(path, {
            "bytes": 2,
            "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        })
        with self.assertRaises(FileNotFoundError):
            build.verify_input(self.root / "missing.json", {"bytes": 2, "sha256": "0" * 64})

    def test_dependency_path_outside_workdir_is_rejected(self):
        packages = [{"Dir": "/old/developer/nitro/arbos", "GoFiles": ["state.go"]}]
        with self.assertRaisesRegex(ValueError, "OUTSIDE_BUILD_ROOT"):
            build.validate_dependency_paths(packages, self.root)

    def test_compiler_diagnostics_cannot_corrupt_structured_stdout(self):
        script = 'import sys; print(\'{"package":"example"}\'); print("download diagnostic", file=sys.stderr)'
        log = build.step(self.root, "graph", [sys.executable, "-c", script], self.root,
                         build.build_environment(self.root, Path("/usr/local/bin")))
        self.assertEqual(log.read_text(), '{"package":"example"}\n')
        self.assertEqual(list(build.json_stream(log.read_text())), [{"package": "example"}])
        self.assertIn("download diagnostic", (self.root / "records/graph.stderr.log").read_text())

    def test_timed_out_build_step_preserves_a_failure_record(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            build.step(self.root, "timeout", [sys.executable, "-c", "import time; time.sleep(10)"],
                       self.root, build.build_environment(self.root, Path("/usr/local/bin")), timeout=0.05)
        path = self.root / "records/timeout.json"
        self.assertTrue(path.exists(), "A timeout must retain the completed child and deadline evidence")
        result = json.loads(path.read_text())
        self.assertTrue(result["timedOut"])
        self.assertNotEqual(result["exitCode"], 0)

    def test_unpinned_go_file_is_rejected_before_staging(self):
        repo = self.root / "checkout"
        native = repo / "native"
        native.mkdir(parents=True)
        (native / "main.go").write_bytes(b"abc")
        (native / "injected.go").write_bytes(b"package main\n")
        lock = {"sourceFiles": [{"path": "native/main.go", "bytes": 3,
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}]}
        with self.assertRaisesRegex(ValueError, "SOURCE_FILE_SET"):
            build.source_pins(repo, lock)

    def test_symlinked_source_directory_is_rejected_before_staging(self):
        repo = self.root / "checkout"
        native = repo / "native"
        native.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "main.go").write_bytes(b"abc")
        (native / "module").symlink_to(outside, target_is_directory=True)
        lock = {"sourceFiles": [{"path": "native/module/main.go", "bytes": 3,
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}]}
        with self.assertRaisesRegex(ValueError, "SYMLINK_SOURCE"):
            build.source_pins(repo, lock)

    def test_active_go_source_is_relocated_without_mutating_checkout(self):
        repo = self.root / "checkout"
        (repo / "native/prestate").mkdir(parents=True)
        (repo / "native/saved-pair").mkdir(parents=True)
        (repo / "native/prestate/go.mod").write_text(
            "module local/rhook-robinhood\nreplace github.com/offchainlabs/nitro => /old/nitro\n"
            "replace github.com/ethereum/go-ethereum => /old/geth\n")
        (repo / "native/saved-pair/go.mod").write_text(
            "module local/rhook-saved-pair\nreplace local/rhook-robinhood => /old/native\n"
            "replace github.com/offchainlabs/nitro => /old/nitro\n"
            "replace github.com/ethereum/go-ethereum => /old/geth\n")
        (repo / "native/saved-pair/main.go").write_text("package main\n")
        work = self.root / "work"
        build.stage_rhook(repo, work)
        self.assertIn("/old/native", (repo / "native/saved-pair/go.mod").read_text())
        staged = work / "src/checkpoint/native/saved-pair"
        self.assertIn("local/rhook-robinhood => ../prestate", (staged / "go.mod").read_text())
        self.assertEqual((staged / "main.go").read_text(), "package main\n")

    def test_staged_go_edit_between_bootstrap_and_build_is_rejected(self):
        self.assertTrue(hasattr(build, "verify_staged_rhook"), "Staged-source verification is not implemented")
        repo = self.root / "checkout"
        for module in ["prestate", "saved-pair"]:
            path = repo / "native" / module
            path.mkdir(parents=True)
            text = ("module local/example\n"
                    "replace github.com/offchainlabs/nitro => /old/nitro\n"
                    "replace github.com/ethereum/go-ethereum => /old/geth\n")
            if module == "saved-pair":
                text += "replace local/rhook-robinhood => /old/native\n"
            (path / "go.mod").write_text(text)
        (repo / "native/saved-pair/main.go").write_text("package main\n")
        lock = {"sourceFiles": [{"path": str(p.relative_to(repo)), "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in (repo / "native").rglob("*") if p.is_file()]}
        work = self.root / "work"
        build.stage_rhook(repo, work)
        build.verify_staged_rhook(repo, work, lock)
        staged = work / "src/checkpoint/native/saved-pair/main.go"
        staged.write_text("package main\nfunc init() {}\n")
        with self.assertRaisesRegex(ValueError, "STAGED_SOURCE"):
            build.verify_staged_rhook(repo, work, lock)


if __name__ == "__main__":
    unittest.main()
