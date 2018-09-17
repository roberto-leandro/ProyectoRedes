import threading
import readline
import socket
import sys


class UDPNode:
    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.reachability_table = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("[IntAS Node]")
        print("Address:", ip)
        print("Port:", port)

    def start_node(self):
        print("START EXECUTED")
        connection_handler_thread =\
            threading.Thread(target=self.handle_incoming_connections)
        connection_handler_thread.start()
        self.handle_console_commands()

    def handle_incoming_connections(self):
        print("LISTENING TO INCOMING CONNECTIONS")
        self.sock.bind((self.ip, self.port))

        while True:
            message, addr = self.sock.recvfrom(1024)
            print(f"MESSAGE FROM {addr}")
            print(f"[NODE] {message}")

    def send_message(self, ip, port, message):
        print(f"[NODE] SENDING {message} TO {ip}:{port}")
        self.sock.settimeout(1.0)
        addr = (ip, port)
        self.sock.sendto(message.encode(), addr)

    def handle_console_commands(self):
        while True:
            command = input("[NODE] Enter your command...\n> ")
            command = command.strip().split(" ")

            if len(command) != 4:
                print("Unrecognized command, try again.")

            if command[0] == "sendMessage":
                self.send_message(ip=command[1],
                                  port=int(command[2]),
                                  message=command[3])
            else:
                print("Unrecognized command, try again.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(sys.argv)
        print(len(sys.argv))
        print("Incorrect arg number")
        sys.exit(1)

    node = UDPNode(sys.argv[1], int(sys.argv[2]))
    node.start_node()
