#!/usr/bin/env python3
import sys
import csv
import os
import multiprocessing
from UDPNode import UDPNode


def spawn_node(node, edges):
    neighbors = dict()
    for (node_a, node_b), cost in edges.items():
        if node_a == node:
            neighbors[node_b] = cost
        elif node_b == node:
            neighbors[node_a] = cost
    ip = node[0]
    mask = node[1]
    port = node[2]
    new_node = UDPNode(ip, mask, port, neighbors)
    new_node.start_node()


def commands_from_csv(csv_file):
    # A graph is set of nodes and edges
    nodes = set()
    edges = dict()
    with open(csv_file, newline="") as csv_file:
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            node_a = (row[0], int(row[1]), int(row[2]))
            node_b = (row[3], int(row[4]), int(row[5]))
            cost = int(row[6])
            nodes.add(node_a)
            nodes.add(node_b)
            edges[tuple([node_a, node_b])] = cost

    for node in nodes:
        this_node = f"{node[0]} {node[1]} {node[2]}"
        neighbors = ""
        for (node_a, node_b), cost in edges.items():
            if node_a == node:
                neighbors += f"{node_b[0]} {node_b[1]} {node_b[2]} {cost} "
            elif node_b == node:
                neighbors += f"{node_a[0]} {node_a[1]} {node_a[2]} {cost} "

        print(f"UDPNode.py {this_node} {neighbors}")

        #os.system(f"start cmd /c UDPNode.py {this_node} {neighbors}")

#"""
        processes = list()
        new_process = multiprocessing.Process(target=spawn_node, args=(node, edges))
        processes.append(new_process)

        for process in processes:
            process.start()
#"""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        commands_from_csv(sys.argv[1])
    else:
        print("ARG!")
