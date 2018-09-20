#!/usr/bin/env python3
import subprocess
import sys

if "readline" in sys.modules:
    import readline  # Nice input() handling

open_processes = {}

intro_text = """\
Available commands are
    exit
    createNode <intAs|pseudoBGP> <address> <port>
"""

if sys.platform in ["linux2", "linux"]:
    def spawn_terminal(file, ip, port):
        return subprocess.Popen(["xterm", "-e", sys.executable, file, ip, port])
elif sys.platform in ["win32", "cygwin"]:
    def spawn_terminal(file, ip, port):
        return subprocess.Popen([sys.executable, file, ip, port],
                                creationflags=subprocess.CREATE_NEW_CONSOLE)
else:
    print("Unsupported OS")

    def spawn_terminal(file, ip, port):
        return None


def create_node(node_type, ip, port):
    if node_type == "intAs":
        script_file = "UDPNode.py"
    elif node_type == "pseudoBGP":
        script_file = "TCPNode.py"
    else:
        print("Unrecognized command, try again.")
        return

    process_key = (ip, port, node_type)
    if process_key in open_processes:
        if open_processes[process_key].poll() is None:
            print(f"ERROR: A {node_type} node is already using {ip}:{port}")
            return
        else:
            print(f"INFO: A {node_type} node was already using {ip}:{port},",
                  "but was terminated")
            open_processes.pop(process_key)

    node_process = spawn_terminal(script_file, ip, str(port))
    open_processes[process_key] = node_process


print(intro_text)
while True:
    # Read a command from the user
    command = input("Enter your command...\n> ").strip().split(" ")

    if len(command) == 1 and command[0] == "exit":
        for _, proc in open_processes.items():
            proc.terminate()
        sys.exit(0)

    if len(command) != 4:
        print("Unrecognized command, try again.")
        continue

    if command[0] == "createNode":
        # Create new process to execute this node
        create_node(node_type=command[1], ip=command[2], port=int(command[3]))
