#!/usr/bin/env python3
"""Pinned macOS arm64 build only. No replay, host admission or authority issuer."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request


REPO = Path(__file__).resolve().parents[1]
LOCK_PATH = Path(__file__).with_name("dependencies.lock.json")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_download(path, pin):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("SYMLINK_DOWNLOAD")
    if "bytes" in pin and path.stat().st_size != pin["bytes"]:
        raise ValueError("DOWNLOAD_SIZE_MISMATCH")
    if sha256(path) != pin["sha256"]:
        raise ValueError("DOWNLOAD_SHA256_MISMATCH")


def download(url, pin, destination):
    if not url.startswith(("https://codeload.github.com/", "https://go.dev/dl/",
                           "https://static.rust-lang.org/dist/")):
        raise ValueError("UNAPPROVED_ARCHIVE_URL")
    destination = Path(destination)
    if destination.exists():
        verify_download(destination, pin)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    # No retry or alternate URL; failed bytes never become a verified archive.
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("xb") as out:
        count = 0
        while chunk := response.read(1 << 20):
            count += len(chunk)
            if count > pin.get("bytes", 512 << 20):
                raise ValueError("DOWNLOAD_SIZE_LIMIT")
            out.write(chunk)
    verify_download(partial, pin)
    partial.rename(destination)
    return destination


def extract_archive(archive, destination):
    """Validate the whole archive, then publish one top directory atomically."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".extract-") as tmp:
        staging = Path(tmp)
        try:
            with tarfile.open(archive) as source:
                members = source.getmembers()
                if len(members) > 100000 or sum(x.size for x in members) > 2 << 30:
                    raise ValueError("ARCHIVE_EXPANSION_LIMIT")
                tops = set()
                for entry in members:
                    path = PurePosixPath(entry.name)
                    if path.is_absolute() or ".." in path.parts or not path.parts:
                        raise ValueError("UNSAFE_ARCHIVE_PATH")
                    tops.add(path.parts[0])
                    # data_filter also handles safe relative upstream symlinks.
                    tarfile.data_filter(entry, str(staging))
                if len(tops) != 1:
                    raise ValueError("ARCHIVE_REQUIRES_ONE_ROOT")
                source.extractall(staging, members=members, filter="data")
        except tarfile.TarError as error:
            raise ValueError("UNSAFE_ARCHIVE: " + str(error)) from error
        top = staging / next(iter(tops))
        if not top.is_dir() or top.is_symlink():
            raise ValueError("ARCHIVE_ROOT_NOT_DIRECTORY")
        # The common top directory is removed when publishing. A link safe inside
        # staging could escape its new root after that move (top/link -> ../x).
        for path in top.rglob("*"):
            if path.is_symlink() and not path.resolve().is_relative_to(top.resolve()):
                raise ValueError("SYMLINK_ESCAPES_PUBLISHED_ARCHIVE_ROOT")
        top.rename(destination)


def module_overlay(text, replacements):
    for module, target in replacements.items():
        if Path(target).is_absolute():
            raise ValueError("REPLACEMENT_MUST_BE_RELATIVE")
        expression = r"(?m)^(replace\s+" + re.escape(module) + r"\s+=>\s+).*$"
        text, count = re.subn(expression, lambda match: match[1] + target, text)
        if count != 1:
            raise ValueError("EXPECTED_ONE_REPLACEMENT: " + module)
    for target in re.findall(r"(?m)^replace\s+\S+\s+=>\s+(\S+)", text):
        if Path(target.strip('"')).is_absolute():
            raise ValueError("UNRELOCATED_ABSOLUTE_REPLACEMENT")
    return text


def relocated_module(module, text):
    replacements = {
        "github.com/ethereum/go-ethereum": "../../../nitro/go-ethereum",
        "github.com/offchainlabs/nitro": "../../../nitro",
    }
    if module == "saved-pair":
        replacements["local/rhook-robinhood"] = "../prestate"
    return module_overlay(text, replacements)


def stage_rhook(repo, work):
    source = Path(work) / "src/checkpoint/native"
    shutil.copytree(Path(repo) / "native", source)
    for module in ["prestate", "saved-pair"]:
        path = source / module / "go.mod"
        path.write_text(relocated_module(module, path.read_text()))


def verify_staged_rhook(repo, work, lock):
    root = work / "src/checkpoint"
    paths = list((root / "native").rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("STAGED_SOURCE_SYMLINK")
    actual = {str(path.relative_to(root)) for path in paths if path.is_file()}
    if actual != {pin["path"] for pin in lock["sourceFiles"]}:
        raise ValueError("STAGED_SOURCE_FILE_SET_MISMATCH")
    verified = []
    for pin in lock["sourceFiles"]:
        path = root / pin["path"]
        if path.name == "go.mod":
            expected = relocated_module(path.parent.name, (repo / pin["path"]).read_text()).encode()
            if path.read_bytes() != expected:
                raise ValueError("STAGED_SOURCE_MODULE_OVERLAY_DRIFT")
        elif path.stat().st_size != pin["bytes"] or sha256(path) != pin["sha256"]:
            raise ValueError("STAGED_SOURCE_SHA256_MISMATCH: " + pin["path"])
        verified.append({"path": pin["path"], "sha256": sha256(path)})
    return verified


def build_environment(work, node_bin):
    work = Path(work).resolve()
    return {
        "PATH": os.pathsep.join([str(work / "toolchains/go/bin"),
                                 str(work / "toolchains/rust/bin"),
                                 str(work / "toolchains/tools/bin"), str(node_bin),
                                 "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"),
        "LANG": "C", "TZ": "UTC", "GOENV": "off", "GOWORK": "off",
        "GOTOOLCHAIN": "local", "GOPATH": str(work / "cache/go"),
        "GOMODCACHE": str(work / "cache/go-mod"), "GOCACHE": str(work / "cache/go-build"),
        "GOPROXY": "https://proxy.golang.org", "GOSUMDB": "sum.golang.org",
        "CGO_ENABLED": "1", "CGO_LDFLAGS": "-Wl,-no_warn_duplicate_libraries",
        "GOMAXPROCS": "2", "GOMEMLIMIT": "1073741824",
        "CARGO_HOME": str(work / "cache/cargo"), "CARGO_BUILD_JOBS": "2",
        "CARGO_TARGET_DIR": str(work / "cache/cargo-target"),
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0", "npm_config_cache": str(work / "cache/npm"),
        "npm_config_userconfig": str(work / "home/npm-user.rc"),
        "npm_config_globalconfig": str(work / "home/npm-global.rc"), "npm_config_audit": "false",
        "npm_config_fund": "false", "RAYON_NUM_THREADS": "2",
    }


def verify_input(path, pin):
    verify_download(Path(path), pin)


def validate_dependency_paths(packages, work):
    work = Path(work).resolve()
    paths = set()
    fields = ["GoFiles", "CgoFiles", "CFiles", "CXXFiles", "MFiles", "HFiles",
              "FFiles", "SFiles", "SysoFiles", "EmbedFiles"]
    for package in packages:
        if package.get("Error") or package.get("DepsErrors"):
            raise ValueError("GO_DEPENDENCY_ERROR")
        if package.get("Dir"):
            directory = Path(package["Dir"]).resolve()
            if not directory.is_relative_to(work):
                raise ValueError("GO_DEPENDENCY_OUTSIDE_BUILD_ROOT: " + str(directory))
            for field in fields:
                for name in package.get(field, []):
                    path = (directory / name).resolve()
                    if not path.is_relative_to(work):
                        raise ValueError("GO_DEPENDENCY_OUTSIDE_BUILD_ROOT: " + str(path))
                    paths.add(path)
    return sorted(paths)


def json_stream(text):
    decoder = json.JSONDecoder()
    while text.strip():
        text = text.lstrip()
        item, end = decoder.raw_decode(text)
        yield item
        text = text[end:]


def record(work, name, value):
    path = work / "records" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def step(work, name, command, cwd, env, timeout=3600):
    print(json.dumps({"stage": name, "state": "started"}), flush=True)
    began = time.monotonic()
    log = work / "records" / (name + ".log")
    diagnostics = work / "records" / (name + ".stderr.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    failure = None
    with log.open("wb") as output, diagnostics.open("wb") as errors:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                stderr=errors, start_new_session=True)
        try:
            proc.wait(timeout=timeout)
        except BaseException as error:
            failure = error
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=5)
    record(work, name + ".json", {"command": [str(x) for x in command],
           "cwd": str(cwd), "exitCode": proc.returncode,
           "wallSeconds": time.monotonic() - began, "log": str(log.relative_to(work)),
           "stderrLog": str(diagnostics.relative_to(work)),
           "timedOut": isinstance(failure, subprocess.TimeoutExpired),
           "ownedChildReaped": proc.returncode is not None})
    if failure is not None:
        raise failure
    if proc.returncode:
        raise RuntimeError("BUILD_STEP_FAILED: " + name + "; see " + str(diagnostics))
    print(json.dumps({"stage": name, "state": "complete"}), flush=True)
    return log


def source_pins(repo, lock):
    native = repo / "native"
    paths = list(native.rglob("*"))
    if native.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("SYMLINK_SOURCE")
    actual = {str(path.relative_to(repo)) for path in paths if path.is_file()}
    if actual != {pin["path"] for pin in lock["sourceFiles"]}:
        raise ValueError("SOURCE_FILE_SET_MISMATCH")
    for pin in lock["sourceFiles"]:
        verify_download(repo / pin["path"], pin)


def prerequisites():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("SUPPORTED_BUILD_TARGET_IS_MACOS_ARM64")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm or not Path("/usr/bin/clang").is_file():
        raise ValueError("REQUIRE_NODE_NPM_AND_XCODE_COMMAND_LINE_TOOLS")
    major = int(subprocess.check_output([node, "--version"]).decode().strip().lstrip("v").split(".")[0])
    if major < 20:
        raise ValueError("REQUIRE_NODE_20_OR_NEWER")
    return Path(node).absolute(), Path(npm).absolute()


def reject_ambient_configuration(work):
    # Cargo discovers config above its working directory even with a new
    # CARGO_HOME. Refuse external ancestor config rather than silently inheriting
    # source replacements, linker wrappers, or developer-specific rustflags.
    for ancestor in [work, *work.parents]:
        for name in ["config", "config.toml"]:
            path = ancestor / ".cargo" / name
            if path.exists() or path.is_symlink():
                raise ValueError("AMBIENT_CARGO_CONFIG: " + str(path))


def bootstrap(repo, work, lock):
    node, npm = prerequisites()
    source_pins(repo, lock)
    reject_ambient_configuration(work)
    work.mkdir(parents=True, exist_ok=False)
    for directory in ["home", "tmp", "records", "src", "downloads", "toolchains"]:
        (work / directory).mkdir()
    env = build_environment(work, node.parent)
    go_archive = download(lock["go"]["url"], lock["go"], work / "downloads/go.tar.gz")
    extract_archive(go_archive, work / "toolchains/go")
    for component in lock["rust"]["components"]:
        name = component["name"]
        archive = download(component["url"], component, work / ("downloads/" + name + ".tar.xz"))
        directory = work / ("toolchains/install-" + name)
        extract_archive(archive, directory)
        step(work, "install-" + name, ["/bin/sh", "install.sh", "--prefix=" + str(work / "toolchains/rust"),
             "--disable-ldconfig"], directory, env)
    for source in lock["sources"]:
        print(json.dumps({"stage": "download-" + source["name"]}), flush=True)
        archive = download(source["archiveUrl"], source, work / ("downloads/" + source["name"] + ".tar.gz"))
        destination = work / "src" / source["destination"]
        if destination.is_dir() and not any(destination.iterdir()):
            destination.rmdir()
        extract_archive(archive, destination)
    stage_rhook(repo, work)
    shutil.copytree(repo / "repro/abi", work / "abi")
    record(work, "BOOTSTRAP_COMPLETE.json", {"lockSha256": sha256(LOCK_PATH),
           "node": str(node), "nodeSha256": sha256(node), "npm": str(npm),
           "nativePairExecuted": False, "sourceCheckpoint": lock["sourceCheckpoint"]})
    print(json.dumps({"bootstrap": "PASS", "workdir": str(work)}), flush=True)


def build_only(repo, work, lock):
    source_pins(repo, lock)
    reject_ambient_configuration(work)
    staged = verify_staged_rhook(repo, work, lock)
    record(work, "STAGED_RHOOK_VERIFIED.json", {"exactFiles": len(staged), "files": staged})
    ready = json.loads((work / "records/BOOTSTRAP_COMPLETE.json").read_text())
    if ready["lockSha256"] != sha256(LOCK_PATH):
        raise ValueError("BOOTSTRAP_LOCK_DRIFT")
    node, npm = prerequisites()
    if str(node) != ready["node"] or sha256(node) != ready["nodeSha256"]:
        raise ValueError("NODE_TOOL_DRIFT")
    env = build_environment(work, node.parent)
    go = work / "toolchains/go/bin/go"
    cargo = work / "toolchains/rust/bin/cargo"
    nitro = work / "src/nitro"
    step(work, "npm-ci", [str(npm), "ci", "--ignore-scripts", "--no-audit", "--no-fund"], work / "abi", env)
    step(work, "generate-abi", [str(node), "generate.mjs", str(nitro)], work / "abi", env)
    step(work, "generate-go", [str(go), "run", "-mod=readonly", "./solgen"], nitro, env)
    step(work, "install-cbindgen", [str(cargo), "install", "--locked", "--version", lock["cbindgen"],
         "--root", str(work / "toolchains/tools"), "cbindgen"], work, env)
    step(work, "build-stylus", [str(cargo), "build", "--locked", "--release", "--lib", "-p", "stylus",
         "--features", "cc_brotli"], nitro, env)
    (nitro / "target/lib").mkdir(parents=True, exist_ok=True)
    (nitro / "target/include").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / "cache/cargo-target/release/libstylus.a", nitro / "target/lib/libstylus.a")
    step(work, "generate-header", [str(work / "toolchains/tools/bin/cbindgen"), "--config", "cbindgen.toml",
         "--crate", "stylus", "--output", str(nitro / "target/include/arbitrator.h")], nitro / "crates/stylus", env)
    for file, pin in lock["expectedGenerated"].items():
        path = nitro / ("target/include/arbitrator.h" if file == "arbitrator.h" else "solgen/go/precompilesgen/precompilesgen.go")
        if sha256(path) != pin:
            raise ValueError("GENERATED_ARTIFACT_MISMATCH: " + file)
    module = work / "src/checkpoint/native/saved-pair"
    graph = step(work, "go-dependencies", [str(go), "list", "-mod=readonly", "-deps", "-json", "."], module, env)
    files = validate_dependency_paths(list(json_stream(graph.read_text())), work)
    record(work, "GO_DEPENDENCIES_VERIFIED.json", {"fileCount": len(files), "allWithinBuildRoot": True,
           "files": [{"path": str(path.relative_to(work)), "sha256": sha256(path)} for path in files]})
    (work / "artifacts").mkdir(exist_ok=True)
    binary = work / "artifacts/rhook-saved-pair"
    step(work, "build-go", [str(go), "build", "-mod=readonly", "-trimpath", "-p", "2", "-o", str(binary), "."], module, env)
    step(work, "binary-metadata", [str(go), "version", "-m", str(binary)], work, env)
    verify_staged_rhook(repo, work, lock)
    record(work, "BUILD_RESULT.json", {"status": "BUILD_ONLY_PASS", "binary": str(binary.relative_to(work)),
           "binarySha256": sha256(binary), "binaryBytes": binary.stat().st_size,
           "libstylusSha256": sha256(nitro / "target/lib/libstylus.a"),
           "target": "darwin/arm64", "allGoDependencyPathsWithinBuildRoot": True,
           "ACTUAL": 0, "BRANCH": 0, "EVM": 0, "hostSensors": 0,
           "providerRPC": 0, "WSS": 0, "externalDelivery": "HOLD",
           "limitations": ["Same Mac OS/SDK; no second-machine or bit-identical build claim.",
                           "Historical embedded plan and supervisor still require separate portable replay preparation and fresh native authorization."]})
    print(json.dumps({"status": "BUILD_ONLY_PASS", "binarySha256": sha256(binary), "nativePairExecuted": False}), flush=True)


def main():
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required for safe archive filtering")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bootstrap", "build", "verify-input"])
    parser.add_argument("--workdir", type=Path, default=REPO / ".build/pair03-macos-arm64")
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    lock = json.loads(LOCK_PATH.read_text())
    work = args.workdir.resolve()
    if args.command == "verify-input":
        if args.input is None:
            parser.error("verify-input requires the separately supplied --input file")
        verify_input(args.input, lock["fixture"])
        print(json.dumps({"inputSha256": lock["fixture"]["sha256"], "verified": True, "executed": False}))
    elif args.command == "bootstrap":
        bootstrap(REPO, work, lock)
    else:
        build_only(REPO, work, lock)


if __name__ == "__main__":
    main()
