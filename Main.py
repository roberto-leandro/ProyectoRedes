#!/usr/bin/env python3
import sys
import csv
import multiprocessing
from UDPNode import UDPNode

try:
    # Nice input() handling
    import readline
except ImportError:
    pass


def spawn_node(node, edges):
    neighbors = dict()
    for (node_a, node_b), cost in edges.items():
        if node_a == node:
            neighbors[node_b] = int(cost)
        elif node_b == node:
            neighbors[node_a] = int(cost)
    ip = node[0]
    mask = int(node[1])
    port = int(node[2])
    new_node = UDPNode(ip, port, mask, neighbors)
    new_node.start_node()


def commands_from_csv(csv_file):
    # A graph is set of nodes and edges
    nodes = set()
    edges = dict()
    with open(csv_file, newline="") as csv_file:
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            node_a = tuple(row[0:3])
            node_b = tuple(row[3:6])
            cost = row[6]
            nodes.add(node_a)
            nodes.add(node_b)
            edges[tuple([node_a, node_b])] = cost

    processes = list()
    for node in nodes:
        new_process = multiprocessing.Process(target=spawn_node, args=(node, edges))
        processes.append(new_process)

    for process in processes:
        process.start()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        commands_from_csv(sys.argv[1])
    else:
        print("ARG!")
