import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
import time
import random
import platform as py_platform
import zipfile

import uuid
# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.download_file import *
from utils.get_platforms import *
from utils.get_versions import *
from utils.get_reseved_ports import *
from utils.platform import *
from backend.utils.state import STATE

import requests
from tqdm import tqdm


def _parse_mc_version(version: str) -> tuple[int, ...]:
    nums: list[int] = []
    for part in version.split('.'):
        try:
            nums.append(int(part))
        except ValueError:
            break
    return tuple(nums)


def get_java_version(version: str) -> int:
    parsed = _parse_mc_version(version)
    if parsed >= (1, 20, 5):
        return 21
    elif parsed >= (1, 17):
        return 17
    else:
        return 8


def _adoptium_platform_triplet() -> tuple[str, str, str]:
    system = py_platform.system().lower()
    machine = py_platform.machine().lower()

    if system.startswith("win"):
        os_name = "windows"
    elif system == "darwin":
        os_name = "mac"
    elif system == "linux":
        os_name = "linux"
    else:
        raise RuntimeError(f"Unsupported OS for JDK download: {system}")

    if machine in {"x86_64", "amd64"}:
        arch = "x64"
    elif machine in {"aarch64", "arm64"}:
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported architecture for JDK download: {machine}")

    return os_name, arch, "zip"


def _find_java_executable(jdk_root: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    direct = jdk_root / "bin" / f"java{suffix}"
    if direct.exists():
        return direct

    for subdir in jdk_root.iterdir():
        if not subdir.is_dir():
            continue
        candidate = subdir / "bin" / f"java{suffix}"
        if candidate.exists():
            return candidate

    raise RuntimeError(f"Java executable not found in {jdk_root}")


def _run_checked(args: list[str], *, cwd: str | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _default_server_icon_source() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "backend" / "assets" / "default-server-icon.png",
        root / "app" / "luna" / "src-tauri" / "icons" / "icon.png",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _ensure_default_server_icon(server_dir: Path) -> None:
    target = server_dir / "server-icon.png"
    if target.exists():
        return

    src = _default_server_icon_source()
    if src is None:
        print("Warning: No default server icon source found; skipping server-icon.png")
        return

    shutil.copyfile(src, target)


def get_forge_installer_url(mc_version: str) -> str:
    """Get the latest Forge installer URL for a given Minecraft version."""
    try:
        # Get promotions data to find the recommended Forge version
        promotions_url = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        response = requests.get(promotions_url)
        promotions = response.json()
        
        # Look for the recommended version for this MC version
        mc_key = f"{mc_version}-recommended"
        if mc_key in promotions["promos"]:
            forge_version = promotions["promos"][mc_key]
            installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{forge_version}/forge-{mc_version}-{forge_version}-installer.jar"
            return installer_url
        else:
            # Fallback: try latest if recommended not found
            mc_key_latest = f"{mc_version}-latest"
            if mc_key_latest in promotions["promos"]:
                forge_version = promotions["promos"][mc_key_latest]
                installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{forge_version}/forge-{mc_version}-{forge_version}-installer.jar"
                return installer_url
            else:
                raise ValueError(f"No Forge version found for Minecraft {mc_version}")
    except Exception as e:
        print(f"Failed to get Forge installer URL: {e}")
        # Fallback to a known working pattern or raise error
        raise ValueError(f"Could not determine Forge installer URL for Minecraft {mc_version}")

def get_neoforge_installer_url(mc_version: str) -> str:
    """Get the NeoForge installer URL for a given version using mcutils API."""
    try:
        import urllib.request
        import json
        
        # Use mcutils API which provides download URLs
        api_url = f"https://mcutils.com/api/server-jars/neoforge/{mc_version}"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode("utf-8"))
            
        # Get the actual download URL from the response
        if "downloadUrl" in data:
            return data["downloadUrl"]
        
        raise ValueError(f"No download URL found for NeoForge version {mc_version}")
    except Exception as e:
        print(f"Failed to get NeoForge installer URL: {e}")
        raise ValueError(f"Could not determine NeoForge installer URL for version {mc_version}")

def download_jdk(version: int, folder: str):
    print(f"Downloading JDK {version}...")
    os_name, arch, image_type = _adoptium_platform_triplet()
    url = f"https://api.adoptium.net/v3/binary/latest/{version}/ga/{os_name}/{arch}/jdk/hotspot/normal/eclipse?project=jdk&image_type={image_type}"
    zip_path = f"{folder}/jdk.zip"
    response = requests.get(url, stream=True)
    response.raise_for_status()
    total_size = int(response.headers.get('content-length', 0))
    with open(zip_path, 'wb') as f, tqdm(
        desc=f"JDK {version}",
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024):
            size = f.write(data)
            bar.update(size)
    print("Extracting JDK...")
    extract_dir = Path(folder) / "jdk"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    os.remove(zip_path)

    java_cmd = _find_java_executable(extract_dir)

    print("JDK downloaded and extracted.")
    return str(java_cmd)

def remove_from_servers_json(folder: str):
    STATE.mutate(lambda servers: [s for s in servers if s.get("folder") != folder])

def server_exists(platform: str, version: str, name: str) -> bool:
    servers = STATE.read()
    for server in servers:
        if server.get("platform") == platform and server.get("version") == version and server.get("name") == name:
            return True
    return False

def update_servers_json(
    edition: str,
    platform: str,
    version: str,
    name: str,
    RAM: int,
    EULA: bool,
    port: int,
    sticky_address: bool = True,
    voice_port: int | None = None,
):
    print("Updating servers.json...")
    servers = STATE.read()

    # Generate a stable ID per installed server instance
    server_id = str(uuid.uuid4())

    # Allocate a per-server Simple Voice Chat UDP port (Java servers only)
    if voice_port is None and edition in ("java", "both"):
        used: set[int] = set()
        try:
            for s in servers:
                vp = s.get("voice_port")
                if isinstance(vp, int):
                    used.add(vp)
                p = s.get("port")
                if isinstance(p, int):
                    used.add(p)
        except Exception:
            pass
        used.add(int(port))

        reserved = []
        try:
            # Local UDP reserved ports (Windows excluded ranges, etc.)
            reserved = get_reserved_ports("udp")
        except Exception:
            reserved = []

        def is_reserved(p: int) -> bool:
            for a, b in reserved:
                if a <= p <= b:
                    return True
            return False

        for _ in range(20000):
            cand = random.randint(24454, 65535)
            if cand in used:
                continue
            if is_reserved(cand):
                continue
            voice_port = cand
            break

        if voice_port is None:
            raise RuntimeError("Could not allocate a free UDP port for Simple Voice Chat")

    server_info = {
        "server_id": server_id,
        "sticky_address": bool(sticky_address),
        "tunneling": True,
        "edition": edition,
        "platform": platform,
        "version": version,
        "name": name,
        "ram": RAM,
        "eula": EULA,
        "folder": f"{platform}-{version}-{name}",
        "port": int(port),
    }

    if voice_port is not None:
        server_info["voice_port"] = int(voice_port)

    servers.append(server_info)
    STATE.write(servers)

def install_server(edition: str, platform: str, version: str, name: str, RAM: int, EULA: bool, sticky_address: bool = True) -> Path:

    print(f"Starting installation of {edition} server: {platform} {version} '{name}' with {RAM}MB RAM, EULA: {EULA}")

    # Check if server already exists
    if server_exists(platform, version, name):
        raise ValueError(f"Server with platform '{platform}', version '{version}', and name '{name}' already exists.")

    # make folder in servers/ for the server files
    # example: servers/paper-1.21.1.jar
    os.makedirs("servers/", exist_ok=True)
    server_folder = Path(f"servers/{platform}-{version}-{name}")
    os.makedirs(server_folder, exist_ok=True)

    # get a list of all used server ports
    used_ports: list[int] = [int(server.get("port", 0)) for server in STATE.read()]

    # get a list of all OS-reserved ports and add them to a seperate list
    if edition in ("java", "both"):
        reserved_ports = get_reserved_ports("tcp")
        for start, end in reserved_ports:
            used_ports.extend(range(start, end + 1))
    elif edition == "bedrock":
        reserved_ports = get_reserved_ports("udp")
        for start, end in reserved_ports:
            used_ports.extend(range(start, end + 1))

    create_port = random.randint(25565, 65535)
    while create_port in used_ports:
        create_port = random.randint(25565, 65535)

    try:
        # Update servers.json with the new server details
        update_servers_json(edition, platform, version, name, RAM, EULA, port=create_port, sticky_address=sticky_address)

        if edition == "java":
            java_download(platform, version, name, RAM, EULA, port=create_port)

        elif edition == "bedrock":
            bedrock_download(name, RAM, EULA)

        elif edition == "both":
            geyser_download(platform, version, name, RAM, EULA)

        _ensure_default_server_icon(server_folder)

        print("Installation completed successfully.")

    except Exception as e:
        # Delete the folder if installation fails
        try:
            shutil.rmtree(server_folder)
        except Exception as cleanup_e:
            print(f"Warning: Could not fully clean up {server_folder}: {cleanup_e}")
        # Remove from servers.json
        remove_from_servers_json(f"{platform}-{version}-{name}")
        raise  # re-raise the exception

    return server_folder

def java_download(platform: str, version: str, name: str, RAM: int, EULA: bool, port: int):
    print("Downloading Java server...")
    if platform not in list_platforms():
        raise ValueError(f"Unsupported platform: {platform}")
    if version not in list_versions(platform):
        raise ValueError(f"Unsupported version: {version} for platform: {platform}")
        
    if not EULA:
        raise ValueError("EULA not accepted")    
    
    # Download the appropriate JDK
    java_version = get_java_version(version)
    server_folder_str = os.path.abspath(f"servers/{platform}-{version}-{name}")
    if not os.path.exists(f"{server_folder_str}/jdk"):
        print(f"Downloading JDK {java_version} for Minecraft {version}...")
        java_cmd = download_jdk(java_version, server_folder_str)
    else:
        print("JDK already exists, finding Java...")
        jdk_dir = f"{server_folder_str}/jdk"
        subdirs = [d for d in os.listdir(jdk_dir) if os.path.isdir(os.path.join(jdk_dir, d))]
        if subdirs:
            jdk_subdir = subdirs[0]
            java_cmd = str(Path(jdk_dir) / jdk_subdir / "bin" / ("java.exe" if os.name == "nt" else "java"))
        else:
            java_cmd = str(Path(jdk_dir) / "bin" / ("java.exe" if os.name == "nt" else "java"))
    
    print(f"Java command: {java_cmd}")
    if not os.path.exists(java_cmd):
        raise RuntimeError(f"Java executable not found at {java_cmd}")
    
    if platform in ["purpur", "paper", "pufferfish", "folia", "vanilla", "velocity", "waterfall", "fabric", "quilt", "forge", "neoforge"]:
        print("Downloading server jar...")

        if platform == "fabric":
            server_dir = Path(f"servers/{platform}-{version}-{name}")
            fabric_filename = f"fabric-server-mc.{version}-loader.0.18.4-launcher.1.1.1.jar"
            fabric_url = f"https://meta.fabricmc.net/v2/versions/loader/{version}/0.18.4/1.1.1/server/jar"
            downloaded = download_file(fabric_url, server_dir / fabric_filename)
            downloaded.rename(server_dir / f"{platform}-{version}.jar")
        elif platform == "quilt":
            # Download Quilt installer
            installer_url = "https://quiltmc.org/api/v1/download-latest-installer/java-universal"
            installer_path = f"servers/{platform}-{version}-{name}/quilt-installer.jar"
            download_file(installer_url, installer_path)
            
            # Run Quilt installer
            print("Running Quilt installer...")
            _run_checked([java_cmd, "-jar", "quilt-installer.jar", "install", "server", version, "--download-server"], cwd=f"servers/{platform}-{version}-{name}")
            
            # Find and rename the server JAR
            server_dir = f"servers/{platform}-{version}-{name}"
            server_subdir = os.path.join(server_dir, "server")
            
            # Check if server subdirectory exists
            if os.path.exists(server_subdir):
                # Move all contents from server/ to the main server directory
                for item in os.listdir(server_subdir):
                    source_path = os.path.join(server_subdir, item)
                    target_path = os.path.join(server_dir, item)
                    if os.path.exists(target_path):
                        # If target exists, remove it first (installer might create duplicates)
                        if os.path.isdir(target_path):
                            shutil.rmtree(target_path)
                        else:
                            os.remove(target_path)
                    shutil.move(source_path, server_dir)
                
                # Remove the now empty server directory
                os.rmdir(server_subdir)
                
                # Rename the launcher JAR
                launcher_jar = os.path.join(server_dir, "quilt-server-launch.jar")
                if os.path.exists(launcher_jar):
                    expected_jar = f"{platform}-{version}.jar"
                    os.rename(launcher_jar, os.path.join(server_dir, expected_jar))
                else:
                    raise RuntimeError("Quilt server launcher JAR not found")
            else:
                raise RuntimeError("Server subdirectory not found after Quilt installation")
        elif platform == "forge":
            # Download Forge installer
            print("Getting Forge installer URL...")
            installer_url = get_forge_installer_url(version)
            installer_path = f"servers/{platform}-{version}-{name}/forge-installer.jar"
            print(f"Downloading Forge installer from {installer_url}...")
            download_file(installer_url, installer_path)
            
            # Run Forge installer
            print("Running Forge installer...")
            _run_checked([java_cmd, "-jar", "forge-installer.jar", "--installServer"], cwd=f"servers/{platform}-{version}-{name}")
            
            # Find the installed server JAR (usually named something like forge-{mc_version}-{forge_version}.jar)
            server_dir = f"servers/{platform}-{version}-{name}"
            jar_files = [f for f in os.listdir(server_dir) if f.endswith(".jar") and "installer" not in f and f.startswith("forge-")]
            if jar_files:
                # Rename the forge JAR to the expected name
                actual_jar = jar_files[0]
                expected_jar = f"{platform}-{version}.jar"
                if actual_jar != expected_jar:
                    os.rename(os.path.join(server_dir, actual_jar), os.path.join(server_dir, expected_jar))
                print(f"Forge server JAR renamed to {expected_jar}")
            else:
                # Check for run.sh/run.bat which indicates successful installation
                run_files = [f for f in os.listdir(server_dir) if f.startswith("run.") and (f.endswith(".sh") or f.endswith(".bat"))]
                if not run_files:
                    raise RuntimeError("Forge installation did not produce expected JAR or run files")
                print("Forge server installed successfully (using run script)")
                # For now, assume the run.bat will be used, but we still need a JAR reference
                # Let's check if there's a minecraft_server JAR or similar
                mc_jar = [f for f in os.listdir(server_dir) if f.endswith(".jar") and "minecraft_server" in f]
                if mc_jar:
                    expected_jar = f"{platform}-{version}.jar"
                    os.rename(os.path.join(server_dir, mc_jar[0]), os.path.join(server_dir, expected_jar))
                else:
                    raise RuntimeError("Could not find Forge server JAR after installation")
            
            # For Forge, copy the shim.jar to the main directory and set up user_jvm_args.txt
            import shutil
            shim_path = f"servers/{platform}-{version}-{name}/libraries/net/minecraftforge/forge/{version}-*/forge-{version}-*-shim.jar"
            import glob
            shim_files = glob.glob(shim_path)
            if shim_files:
                shutil.copy2(shim_files[0], f"servers/{platform}-{version}-{name}/")
                print("Copied Forge shim.jar to main directory")
            
            # Set up user_jvm_args.txt with correct memory settings
            user_jvm_args_path = f"servers/{platform}-{version}-{name}/user_jvm_args.txt"
            if os.path.exists(user_jvm_args_path):
                with open(user_jvm_args_path, 'r') as f:
                    content = f.read()
                # Replace or add memory settings
                content = content.replace('# -Xmx4G', f'-Xmx{RAM}M\n-Xms{RAM}M')
                if '-Xmx' not in content:
                    content += f'\n-Xmx{RAM}M\n-Xms{RAM}M'
                with open(user_jvm_args_path, 'w') as f:
                    f.write(content)
                print("Updated user_jvm_args.txt with memory settings")
        elif platform == "neoforge":
            # Download NeoForge installer
            print("Getting NeoForge installer URL...")
            installer_url = get_neoforge_installer_url(version)
            installer_path = f"servers/{platform}-{version}-{name}/neoforge-installer.jar"
            print(f"Downloading NeoForge installer from {installer_url}...")
            download_file(installer_url, installer_path)
            
            # Run NeoForge installer
            print("Running NeoForge installer...")
            _run_checked([java_cmd, "-jar", "neoforge-installer.jar", "--installServer"], cwd=f"servers/{platform}-{version}-{name}")
            
            # NeoForge doesn't create a single JAR file like Forge does
            # Instead, it creates run.bat/run.sh scripts and a libraries directory
            # Check that installation was successful by verifying run files exist
            server_dir = f"servers/{platform}-{version}-{name}"
            run_files = [f for f in os.listdir(server_dir) if f.startswith("run.") and (f.endswith(".sh") or f.endswith(".bat"))]
            if not run_files:
                raise RuntimeError("NeoForge installation did not produce expected run files")
            
            print("NeoForge server installed successfully (using run script)")
            
            # Set up user_jvm_args.txt with correct memory settings
            user_jvm_args_path = f"servers/{platform}-{version}-{name}/user_jvm_args.txt"
            if os.path.exists(user_jvm_args_path):
                with open(user_jvm_args_path, 'r') as f:
                    content = f.read()
                # Replace or add memory settings
                content = content.replace('# -Xmx4G', f'-Xmx{RAM}M\n-Xms{RAM}M')
                if '-Xmx' not in content:
                    content += f'\n-Xmx{RAM}M\n-Xms{RAM}M'
                with open(user_jvm_args_path, 'w') as f:
                    f.write(content)
                print("Updated user_jvm_args.txt with memory settings")
                print("Updated user_jvm_args.txt with memory settings")
        else:
            # First, get the download URL from the API
            api_url = f"https://mcutils.com/api/server-jars/{platform}/{version}"
            data = http_get_json(api_url)
            download_url = data["downloadUrl"]
            
            download_file(download_url, f"servers/{platform}-{version}-{name}/{platform}-{version}.jar")

        jar_path = f"servers/{platform}-{version}-{name}/{platform}-{version}.jar"
        print(f"JAR path: {jar_path}")
        if platform not in ["forge", "neoforge"] and not os.path.exists(jar_path):
            raise RuntimeError(f"JAR file not found at {jar_path}")

        print("Running server for initial setup...")
        if platform in ["forge", "neoforge"]:
            run_bat = f"servers/{platform}-{version}-{name}/run.bat"
            if os.path.exists(run_bat):
                _run_checked(["cmd", "/c", "run.bat", "nogui"], cwd=f"servers/{platform}-{version}-{name}")
            else:
                _run_checked([java_cmd, f"-Xmx{RAM}M", f"-Xms{RAM}M", "-jar", f"{platform}-{version}.jar", "nogui"], cwd=f"servers/{platform}-{version}-{name}")
        else:
            _run_checked([
                java_cmd,
                f"-Xmx{RAM}M",
                f"-Xms{RAM}M",
                "-XX:+UseG1GC",
                "-XX:+ParallelRefProcEnabled",
                "-XX:MaxGCPauseMillis=200",
                "-XX:+UnlockExperimentalVMOptions",
                "-XX:+DisableExplicitGC",
                "-XX:+AlwaysPreTouch",
                "-XX:G1NewSizePercent=30",
                "-XX:G1MaxNewSizePercent=40",
                "-XX:G1HeapRegionSize=8M",
                "-XX:G1ReservePercent=20",
                "-XX:G1HeapWastePercent=5",
                "-XX:G1MixedGCCountTarget=4",
                "-XX:InitiatingHeapOccupancyPercent=15",
                "-XX:G1MixedGCLiveThresholdPercent=90",
                "-XX:G1RSetUpdatingPauseTimePercent=5",
                "-XX:SurvivorRatio=32",
                "-XX:+PerfDisableSharedMem",
                "-XX:MaxTenuringThreshold=1",
                "-Daikars.new.flags=true",
                "-Dusing.aikars.flags=https://mcutils.com",
                "-jar",
                f"{platform}-{version}.jar",
                "--nogui",
            ], cwd=f"servers/{platform}-{version}-{name}")
        
        with open(f"servers/{platform}-{version}-{name}/eula.txt", "w") as f:
            f.write("eula=true\n")

    elif platform in ["spigot", "craftbukkit"]:
        print("Downloading BuildTools...")
        #First, download the buildtools jar
        download_file("https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar", Path(f"servers/{platform}-{version}-{name}") / "BuildTools.jar")
        # Then, run buildtools to generate the server jar
        print("Building server with BuildTools...")
        _run_checked([java_cmd, "-jar", "BuildTools.jar", "--rev", version, "--compile", platform], cwd=f"servers/{platform}-{version}-{name}")
        
        # Find the built JAR
        server_dir = f"servers/{platform}-{version}-{name}"
        jar_files = [f for f in os.listdir(server_dir) if f.startswith(f"{platform}-") and f.endswith(".jar")]
        if not jar_files:
            raise RuntimeError("No JAR file found after building with BuildTools")
        actual_jar = jar_files[0]
        expected_jar = f"{platform}-{version}.jar"
        if actual_jar != expected_jar:
            raise RuntimeError(f"Built JAR version mismatch: expected {expected_jar}, got {actual_jar}. BuildTools may not support this version.")
        print(f"Built JAR: {actual_jar}")
        
        print("Running server for initial setup...")
        # Run the server to generate initial files
        _run_checked([
            java_cmd,
            f"-Xmx{RAM}M",
            f"-Xms{RAM}M",
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+DisableExplicitGC",
            "-XX:+AlwaysPreTouch",
            "-XX:G1NewSizePercent=30",
            "-XX:G1MaxNewSizePercent=40",
            "-XX:G1HeapRegionSize=8M",
            "-XX:G1ReservePercent=20",
            "-XX:G1HeapWastePercent=5",
            "-XX:G1MixedGCCountTarget=4",
            "-XX:InitiatingHeapOccupancyPercent=15",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:SurvivorRatio=32",
            "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=1",
            "-Daikars.new.flags=true",
            "-Dusing.aikars.flags=https://mcutils.com",
            "-jar",
            actual_jar,
            "--nogui",
        ], cwd=f"servers/{platform}-{version}-{name}")
        
        with open(f"servers/{platform}-{version}-{name}/eula.txt", "w") as f:
            f.write("eula=true\n")

    # change server.properties to use the created port
    properties_path = f"servers/{platform}-{version}-{name}/server.properties"
    if os.path.exists(properties_path):
        with open(properties_path, "r") as f:
            lines = f.readlines()
        with open(properties_path, "w") as f:
            for line in lines:
                if line.startswith("server-port="):
                    f.write(f"server-port={port}\n")
                else:
                    f.write(line)
        print(f"Set server port to {port} in server.properties")



def _jar_looks_like_plugin(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
        return "plugin.yml" in names or "paper-plugin.yml" in names
    except Exception:
        return False


def _pick_geyser_plugin_url(mc_version: str) -> str:
    base = "https://api.modrinth.com/v2/project/geyser/version"
    try:
        # Prefer current game version and bukkit-style loader artifacts first.
        versions = http_get_json(base)
    except Exception as e:
        raise RuntimeError(f"Could not fetch Geyser versions from Modrinth: {e}")

    if not isinstance(versions, list) or not versions:
        raise RuntimeError("Could not fetch Geyser versions from Modrinth")

    preferred_loaders = {"paper", "purpur", "spigot", "bukkit"}

    def score(version_obj: dict) -> tuple[int, int]:
        loaders = set(version_obj.get("loaders") or [])
        game_versions = set(version_obj.get("game_versions") or [])
        return (1 if mc_version in game_versions else 0, 1 if loaders.intersection(preferred_loaders) else 0)

    for version_obj in sorted(versions, key=score, reverse=True):
        files = version_obj.get("files")
        if not isinstance(files, list):
            continue
        for file_obj in files:
            if not isinstance(file_obj, dict):
                continue
            filename = str(file_obj.get("filename", "")).lower()
            if not filename.endswith(".jar"):
                continue
            url = file_obj.get("url")
            if isinstance(url, str) and url:
                return url

    raise RuntimeError("No downloadable Geyser plugin file found")

def bedrock_download(name: str, RAM: int, EULA: bool):
    print("Downloading Bedrock server...")
    if os.name != 'nt':
        raise RuntimeError("Bedrock server installation is only supported on Windows.")
    if not EULA:
        raise ValueError("EULA not accepted")

    server_dir = Path(f"servers/bedrock-bedrock-{name}")
    zip_path = server_dir / "bedrock-server.zip"
    download_file("https://www.minecraft.net/bedrockdedicatedserver/bin-win/bedrock-server-1.21.132.3.zip", zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(server_dir)
    zip_path.unlink(missing_ok=True)

    proc = subprocess.Popen(["bedrock_server.exe"], cwd=str(server_dir))
    time.sleep(10)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
def geyser_download(platform: str, version: str, name: str, RAM: int, EULA: bool):
    print("Installing 'both' edition (Java + Geyser bridge)...")

    # Install Java server first. Port is set by install_server() in servers.json and updated below.
    server_record = None
    for server in STATE.read():
        if server.get("platform") == platform and server.get("version") == version and server.get("name") == name:
            server_record = server
            break
    if server_record is None:
        raise RuntimeError("Server record missing during Geyser install")

    java_download(platform, version, name, RAM, EULA, port=int(server_record["port"]))

    server_dir = Path(f"servers/{platform}-{version}-{name}")
    plugins_dir = server_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    geyser_path = plugins_dir / "Geyser-Spigot.jar"
    geyser_url = _pick_geyser_plugin_url(version)
    download_file(geyser_url, geyser_path)
    if not _jar_looks_like_plugin(geyser_path):
        raise RuntimeError(
            "Downloaded Geyser artifact is not a Bukkit/Paper plugin jar (plugin.yml missing)."
        )

    # Configure Bedrock port so both Java + Bedrock can run from same managed server.
    bedrock_port = int(server_record["port"])
    geyser_config = plugins_dir / "Geyser-Spigot" / "config.yml"
    if geyser_config.exists():
        lines = geyser_config.read_text(encoding="utf-8", errors="ignore").splitlines()
        out: list[str] = []
        changed = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("port:") and line.startswith("  "):
                out.append(f"  port: {bedrock_port}")
                changed = True
            else:
                out.append(line)
        if not changed:
            out.append("bedrock:")
            out.append(f"  port: {bedrock_port}")
        geyser_config.write_text("\n".join(out) + "\n", encoding="utf-8")

    print("Geyser plugin installed. 'both' server is ready.")

    
