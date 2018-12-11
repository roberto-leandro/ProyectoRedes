import struct
import threading
import UDPNode as Constants

logging_lock = threading.Lock()
PRINT_UPDATES = True

def log_message(message, node):
    with logging_lock:
        # with open(f"node_{node.ip}_{node.port}_log.txt", "a+") as log_file:
        #     log_file.write(message + "\n")
        if node.print_updates:
            print(message)


def log_message_force(message, node):
    with logging_lock:
        # with open(f"node_{node.ip}_{node.port}_log.txt", "a+") as log_file:
        #    log_file.write(message + "\n")
        print(message)


def encode_tuple(ip, port, net_mask, cost):
    message = bytearray(Constants.TUPLE_SIZE)
    # Each tuple is encoded with the following 10-byte format:
    # BBBB (4 bytes) ip address (one B byte for each integer in the address)
    #  B   (1 byte)  subnet mask
    #  H   (2 bytes) port
    #  I   (4 bytes) cost
    #      The cost should only be 3 (not 4) bytes, this is handled below.
    struct.pack_into('!BBBBBH', message, 0,
                     ip[0], ip[1],
                     ip[2], ip[3],
                     net_mask, port)

    # Pack the cost into a 4 byte buffer
    cost_bytes = struct.pack('!I', cost)

    # Write the cost into the message buffer, copying only 3 bytes and omitting 1
    # The least significant byte is the one omitted because its encoded as big endian
    message[7:] = cost_bytes[1:]

    return message