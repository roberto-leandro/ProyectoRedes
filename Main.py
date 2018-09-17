from multiprocessing import Process
from TCPNode import TCPNode
from UDPNode import UDPNode
import os

def create_node(node_type, ip, port):
    if node_type == "intAs":
        node = UDPNode(ip, port)
    elif node_type == "pseudoBGP":
        node = TCPNode(ip, port)
    else:
        print("Unrecognized command, try again.")
        return
    node_process = Process(target=node.start_node())

while True:
    # Read a command from the user
    command = input("[MAIN] Enter your command...\n").strip().split(" ")

    if len(command) != 4:
        print("Unrecognized command, try again.")
        continue

    if command[0] == "createNode":
        # Create new process to execute this node
        create_node(node_type=command[1], ip=command[2], port=int(command[3]))





