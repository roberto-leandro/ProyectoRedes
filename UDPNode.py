import socket


class UDPNode:
    def __init__(self, ip, port):
        self.port = port
        self.ip = ip
        self.reachability_table = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("CONSTRUCTOR EXECUTED")

    def start(self):
        print("START EXECUTED")


        self.sock.bind((self.ip, self.port))
        self.sock
