import struct
import threading
import UDPNode as Constants

logging_lock = threading.Lock()


def log_message(message):
    with logging_lock:
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


def __get_valid_message_input():
    def get_input():
        new_input = input("Type the message to be sent as follows:\n" +
                          "<IP address> <subnet mask> <cost>\n")
        new_input = new_input.strip().split(' ')
        return new_input

    while True:
        message = get_input()
        if len(message) != 3:
            print("Wrong number of tokens, expected 3 tokens with the format:")
            print("x.x.x.x x x     Where x is a positive integer")
            continue

        address_token_list = message[0].strip().split('.')
        try:
            address_token_list = [int(tok) for tok in address_token_list]
            net_mask = int(message[1])
            cost = int(message[2])
        except ValueError:
            print("Unexpected input, expected input with format:")
            print("x.x.x.x x x     Where x is a positive integer")
            continue

        if len(address_token_list) != 4:
            print("Invalid address, expected address with format: x.x.x.x")
            continue

        is_address_valid = True
        for token in address_token_list:
            if token > 255:
                print("Invalid address token, must be less than 255")
                is_address_valid = False
                break
            elif token < 0:
                print("Invalid address token, must be a positive integer")
                is_address_valid = False
                break
        if not is_address_valid:
            continue

        if net_mask > 32:
            print("Invalid network mask, expected less than 32")
            continue
        elif net_mask < 0:
            print("Network mask must be a positive integer")
            continue

        if cost < 0:
            print("Invalid cost, must be a positive integer")
            continue
        elif cost > 0xFF_FF_FF:  # max three bytes
            print("Invalid cost, max number exceeded")
            continue

        return address_token_list, net_mask, cost