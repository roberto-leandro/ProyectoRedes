#!/usr/bin/env python3
import subprocess
import readline  # Nice input() handling
import sys


def create_node(node_type, ip, port):
    if node_type == "intAs":
        script_file = "UDPNode.py"
    elif node_type == "pseudoBGP":
        script_file = "TCPNode.py"
    else:
        print("Unrecognized command, try again.")
        return

    print(script_file)
    node_process = subprocess.Popen(
        ["xterm", "-e", "python3", script_file, ip, str(port)])
    print(node_process)


while True:
    # Read a command from the user
    command = input("[MAIN] Enter your command...\n> ").strip().split(" ")

    if len(command) == 1 and command[0] == "exit":
        # TODO: close all the processes
        sys.exit(0)

    if len(command) != 4:
        print("Unrecognized command, try again.")
        continue

    if command[0] == "createNode":
        # Create new process to execute this node
        create_node(node_type=command[1], ip=command[2], port=int(command[3]))
