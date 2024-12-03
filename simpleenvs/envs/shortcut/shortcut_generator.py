import random
import pygame

import numpy as np
import networkx as nx

from typing import List, Tuple

# This class generates a "shortcut" world.
# The world consists of a series of k grids, each progressively smaller (but costlier to move around) than the last.
# The agent must navigate from a start location to a goal location on the first (largest) grid.
# Some positions on each grid allow the agent to move up or down a level to a different grid. These connections act
# as shortcuts, allowing the agent to navigate the world in fewer steps.
# Moving around the different grids can be thought of as using different modes of transport. For instance,
#    - the first grid can be thought of as walking,
#    - the second grid can be thought of as driving, and
#    - the third grid can be thought of as flying.
# The grids are not always perfectly regular - some cells might be blocked. However, each grid is guarunteed to be
# fully connected (i.e., there is a path between any two cells). A parameter controls the probability of a cell being blocked.


class ShortcutGenerator:
    def __init__(
        self,
        num_grids: int,
        grid_sizes: List[int],
        grid_costs: List[int],
        connection_prob: float,
        min_connections: List[int],
        blocker_probs: List[int],
    ):
        self.num_grids = num_grids
        self.grid_sizes = grid_sizes
        self.grid_costs = grid_costs
        self.connection_prob = connection_prob
        self.min_connections = min_connections
        self.blocker_probs = blocker_probs

        self.grids: List[nx.Graph] = []
        self.connections: List[int, Tuple[int, int], int, Tuple[int, int]] = []

    def generate_grids(self):
        # Create a fully-connected graph for each grid. Each cell is a node, connected to adjacent cells by edges.
        self.grids = [
            nx.grid_2d_graph(self.grid_sizes[i][0], self.grid_sizes[i][1], create_using=nx.Graph)
            for i in range(self.num_grids)
        ]

        # Probabilistically remove some nodes from each grid.
        for i in range(len(self.grids)):
            num_nodes_to_remove = int(self.blocker_probs[i] * self.grids[i].order())
            if num_nodes_to_remove > 0:
                self.grids[i], _ = self._remove_n_nodes_preserving_connectivity(self.grids[i], num_nodes_to_remove)

        # for i in range(self.num_grids):
        #     # Iterate over all nodes in the graph in a random order.
        #     nodes = list(self.grids[i].nodes())
        #     random.shuffle(nodes)
        #     for node in nodes:
        #         # Attempt to remove them with probability blocker_prob.
        #         if random.random() < self.blocker_probs[i]:
        #             self._remove_node_preserving_connectivity(self.grids[i], node)

        # Sanity check: ensure that each grid is still connected.
        for i in range(self.num_grids):
            print(f"Grid {i} has {len(list(nx.connected_components(self.grids[i])))} connected components.")
            nx.write_gexf(self.grids[i], f"grid_{i}.gexf")
            assert nx.is_connected(self.grids[i])

        # Generate connections between grids.
        for i in range(1, self.num_grids):
            num_connections = 0
            while num_connections < self.min_connections[i - 1]:
                # Iterate over all cells in the grid in a random order.
                nodes = list(self.grids[i - 1].nodes())
                random.shuffle(nodes)
                for node in nodes:
                    # With some small probability, we want to connect a cell from a lower grid to a cell in a higher grid.
                    # The connections should take into account relative positions on each of the grids. For instance, a cell
                    # near the top right of a lower grid should connect to a cell near the top right of a higher grid (with some noise).
                    if random.random() < self.connection_prob:
                        lower_x, lower_y = node

                        lower_grid_size = self.grid_sizes[i - 1]
                        higher_grid_size = self.grid_sizes[i]

                        lower_grid_x_rel = lower_x / lower_grid_size[0]
                        lower_grid_y_rel = lower_y / lower_grid_size[1]

                        higher_x = int(lower_grid_x_rel * higher_grid_size[0] + random.gauss(0, 0.1))
                        higher_y = int(lower_grid_y_rel * higher_grid_size[1] + random.gauss(0, 0.1))

                        # If the higher-level cell is valid, add the connection.
                        if (higher_x, higher_y) in self.grids[i].nodes():
                            self.connections.append((i - 1, (lower_x, lower_y), i, (higher_x, higher_y)))
                            num_connections += 1

        # Construct a graph of the entire world, with each grid and the connections between.

        # Add the nodes making up each grid.
        self.world = nx.DiGraph()
        for i in range(self.num_grids):
            for node in self.grids[i].nodes():
                x, y = node

                # Add the node to the world.
                self.world.add_node((i, (x, y)))

                # Add edges to adjacent nodes in the world.
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:  # Right, left, down, up
                    if (x + dx, y + dy) in self.grids[i].nodes():
                        self.world.add_edge((i, (x, y)), (i, (x + dx, y + dy)))

        # Add the connections between grids.
        for connection in self.connections:
            lower_grid, (lower_x, lower_y), higher_grid, (higher_x, higher_y) = connection
            self.world.add_edge((lower_grid, (lower_x, lower_y)), (higher_grid, (higher_x, higher_y)))
            self.world.add_edge((higher_grid, (higher_x, higher_y)), (lower_grid, (lower_x, lower_y)))

        # Convert the world to an directed graph.
        self.world = nx.DiGraph(self.world)

        # Sanity check: ensure that the world is still connected.
        assert nx.is_strongly_connected(self.world)

        # Save the graph as a gexf.
        nx.write_gexf(self.world, "shortcut_world.gexf")

    def render(self):
        # Render the grids and the connections between them using pygame.
        # Lower-level (larger) grids should be rendered above higher-level (smaller) grids.
        # Render them as a graph, with each cell as a node and each connection as an edge.
        # Connections between grids should be rendered as a line connecting the two cells on the different grids.
        # It should be projected onto the screen as if the grids were stacked on top of each other.

        # Set up the pygame window.
        pygame.init()
        pygame.display.set_caption("Shortcut World")

        # Set up some colours.
        # BLACK = (0, 0, 0)
        WHITE = (255, 255, 255)
        RED = (255, 0, 0)
        # GREEN = (0, 255, 0)
        # BLUE = (0, 0, 255)

        # Set up some parameters for rendering.
        cell_size = 8
        grid_spacing = 32
        grid_offset = 32

        width = max([size[1] for size in self.grid_sizes]) * cell_size + grid_offset * 2
        height = (
            sum([size[0] for size in self.grid_sizes]) * cell_size
            + grid_spacing * (self.num_grids - 1)
            + grid_offset * 2
        )

        screen = pygame.display.set_mode((width, height))

        # Draw the grids.
        for i in range(self.num_grids):
            for node in self.grids[i].nodes():
                x, y = node

                # Draw the cell.
                base_height = sum([size[0] for size in self.grid_sizes[:i]]) * cell_size + grid_offset
                pygame.draw.rect(
                    screen,
                    WHITE,
                    (
                        grid_offset + x * cell_size,
                        base_height + y * cell_size + grid_spacing * i,
                        cell_size,
                        cell_size,
                    ),
                )

        # Draw the connections between grids.
        for connection in self.connections:
            lower_grid, (lower_x, lower_y), higher_grid, (higher_x, higher_y) = connection

            base_height_lower = sum([size[0] for size in self.grid_sizes[:lower_grid]]) * cell_size + grid_offset
            base_height_higher = sum([size[0] for size in self.grid_sizes[:higher_grid]]) * cell_size + grid_offset

            # Draw the connection.
            pygame.draw.line(
                screen,
                RED,
                (
                    grid_offset + lower_x * cell_size + cell_size // 2,
                    lower_grid * grid_spacing + base_height_lower + lower_y * cell_size + cell_size // 2,
                ),
                (
                    grid_offset + higher_x * cell_size + cell_size // 2,
                    higher_grid * grid_spacing + base_height_higher + higher_y * cell_size + cell_size // 2,
                ),
                width=2,
            )

        # Update the display.
        pygame.display.update()

        # Wait for the user to close the window.
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

    def seed(self, seed):
        random.seed(seed)
        np.random.seed(seed)

    def _remove_n_nodes_preserving_connectivity(self, graph: nx.Graph, n: int) -> Tuple[nx.Graph, int]:
        # Ensure the graph has at least two nodes.
        if graph.order() < 2:
            raise ValueError("Cannot remove nodes from graph with fewer than two nodes.")

        # Ensure the number of nodes to remove is valid.
        if n < 1:
            raise ValueError("Number of nodes to remove must be at least one.")

        # Ensure the number of nodes to remove is not greater than the number of nodes in the graph.
        if n >= graph.order():
            raise ValueError("Number of nodes to remove must be less than the number of nodes in the graph.")

        # Ensure that the graph is connected to begin with.
        if not nx.is_connected(graph):
            raise ValueError("Input graph must be connected.")

        # Pre-compute the initial set of articulation points.
        articulation_points = set(nx.articulation_points(graph))
        removed_nodes_count = 0

        for _ in range(n):
            removable_nodes = [node for node in graph.nodes() if node not in articulation_points]

            # If no removable nodes are left, terminate early.
            if len(removable_nodes) == 0:
                break

            # Remove a random removable node.
            node_to_remove = random.choice(removable_nodes)
            graph.remove_node(node_to_remove)
            removed_nodes_count += 1

            # Update the set of articulation points.
            if graph.order() > 1:
                articulation_points = set(nx.articulation_points(graph))
            else:
                articulation_points = set()

        return graph, removed_nodes_count


if __name__ == "__main__":
    generator = ShortcutGenerator(3, [(50, 50), (20, 20), (3, 3)], [-1, -3, -5], 0.01, [8, 4], [0.5, 0.3, 0.0])
    generator.generate_grids()
    generator.render()
