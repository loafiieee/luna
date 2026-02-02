import json
import os
import subprocess
import asyncio
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.tunnel import TunnelRunner

TUNNEL = TunnelRunner(
    edge_url="wss://tunnel.loafiieee.com",
    domain_suffix="mc.loafiieee.com",
    on_status=lambda s: print(f"[tunnel] {s}"),
)

def read_servers_file() -> list:
    with open("servers/servers.json", "r") as f:
        return json.load(f)
    
def get_per_server_config(platform: str, version: str, name: str) -> dict:
    servers = read_servers_file()
    for server in servers:
        if (server["platform"] == platform and
            server["version"] == version and
            server["name"] == name):
            return server
    raise ValueError(f"No configuration found for server: {platform}-{version}-{name}")

def run_server(edition: str, platform: str, version: str, name: str):
    server_config = get_per_server_config(platform, version, name)
    ram = server_config.get("ram")
    eula = server_config.get("eula")
    folder = server_config.get("folder")
    print(f"Running {edition} server: {platform}-{version}-{name} with {ram}MB RAM and EULA accepted: {eula}")

    # --- Start tunnel based on edition ---
    try:
        if edition == "java":
            info = TUNNEL.start(tcp_local=25565)
            print(f"[tunnel] Java join: {info.public_tcp_address}")

        elif edition == "bedrock":
            info = TUNNEL.start(udp_local=19132)
            print(f"[tunnel] Bedrock join: {info.public_udp_address}")

        elif edition == "both":
            info = TUNNEL.start(tcp_local=25565, udp_local=19132)
            print(f"[tunnel] Java join: {info.public_tcp_address}")
            print(f"[tunnel] Bedrock join: {info.public_udp_address}")

    except Exception as e:
        print(f"[tunnel] ERROR starting tunnel: {e}")
        # You can choose to continue launching the server anyway, or return.
        # return

    if edition == "java":
        server_dir = f"servers/{folder}"
        
        if platform in ["forge", "neoforge"]:
            # For Forge/NeoForge servers, use the run.bat script which sets up the classpath properly
            run_bat = os.path.join(server_dir, "run.bat")
            if os.path.exists(run_bat):
                print(f"Using {platform.capitalize()} run.bat script...")
                # Update user_jvm_args.txt with correct RAM settings
                user_jvm_args = os.path.join(server_dir, "user_jvm_args.txt")
                if os.path.exists(user_jvm_args):
                    with open(user_jvm_args, 'r') as f:
                        content = f.read()
                    # Update memory settings
                    import re
                    content = re.sub(r'-Xmx\d+[GM]', f'-Xmx{ram}M', content)
                    content = re.sub(r'-Xms\d+[GM]', f'-Xms{ram}M', content)
                    # Make sure memory settings are not commented
                    if content.strip().startswith('#'):
                        content = content.replace('# -Xmx', '-Xmx').replace('# -Xms', '-Xms')
                    with open(user_jvm_args, 'w') as f:
                        f.write(content)
                subprocess.run('run.bat nogui', shell=True, cwd=server_dir)
            else:
                # Fallback to direct JAR execution
                print("run.bat not found, falling back to direct JAR execution...")
                jdk_dir = os.path.join(server_dir, "jdk")
                subdirs = [d for d in os.listdir(jdk_dir) if os.path.isdir(os.path.join(jdk_dir, d))]
                if subdirs:
                    jdk_subdir = subdirs[0]
                    java_cmd = os.path.join(jdk_dir, jdk_subdir, "bin", "java.exe")
                else:
                    java_cmd = os.path.join(jdk_dir, "bin", "java.exe")
                subprocess.run(f'"{java_cmd}" -Xmx{ram}M -Xms{ram}M -jar {platform}-{version}.jar nogui', shell=True, cwd=server_dir)
        else:
            jdk_dir = os.path.join(server_dir, "jdk")
            subdirs = [d for d in os.listdir(jdk_dir) if os.path.isdir(os.path.join(jdk_dir, d))]
            if subdirs:
                jdk_subdir = subdirs[0]
                java_cmd = os.path.join(jdk_dir, jdk_subdir, "bin", "java.exe")
            else:
                java_cmd = os.path.join(jdk_dir, "bin", "java.exe")
            subprocess.run(f'"{java_cmd}" -Xmx{ram}M -Xms{ram}M -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -Daikars.new.flags=true -Dusing.aikars.flags=https://mcutils.com -jar {platform}-{version}.jar --nogui', cwd=server_dir, check=False)
    elif edition == "bedrock":
        os.system(f'cd servers/{folder} && bedrock_server.exe')
    elif edition == "both":
        print("Both edition server running is not yet implemented.")