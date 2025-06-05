from typing import override
from aegis import (
    END_TURN, MOVE, SLEEP, SAVE_SURV, SEND_MESSAGE, SEND_MESSAGE_RESULT,
    TEAM_DIG, AgentCommand, AgentIDList, AgentID, World, Cell, Direction,
    Rubble, Survivor, Location, create_location
)
from mas.agent import BaseAgent, Brain, AgentController
from heapq import heappush, heappop


class CoordinatedAgent(Brain):
    NUM_AGENTS = 7

    def __init__(self) -> None:
        super().__init__()
        self._agent: AgentController = BaseAgent.get_agent()
        self._locs_with_survs_and_amount: dict[Location, int] = {}
        self._visited_locations: set[Location] = set()
        self._agent_locations: list[Location | None] = [None] * self.NUM_AGENTS
        self._current_goal: Location | None = None
        self._is_leader: bool = False
        self._leader_id: int = 1
        self._help_assignments: dict[Location, AgentID] = {}

    @override
    # Handles incoming messages from other agents.
# Based on the type of message (e.g., MOVE, HELP, GOTO), performs appropriate action.
def handle_send_message_result(self, smr: SEND_MESSAGE_RESULT) -> None:
        self._agent.log(f"Message received: {smr.msg}")
        parts = smr.msg.strip().split()
        if not parts:
            return

        msg_type = parts[0]

        if msg_type == "MOVE":
            self._current_goal = create_location(int(parts[1]), int(parts[2]))

        elif msg_type == "INIT":
            aid = int(parts[1])
            self._agent_locations[aid - 1] = create_location(int(parts[2]), int(parts[3]))

        elif msg_type == "HELP":
            if self._is_leader:
                agent_id = int(parts[1])
                location = create_location(int(parts[2]), int(parts[3]))
                if location not in self._help_assignments:
                    for i in range(self.NUM_AGENTS):
                        if self._agent.get_agent_id().id != i + 1 and self._agent_locations[i]:
                            self._agent.send(SEND_MESSAGE(
                                AgentIDList([AgentID(i + 1, 1)]), f"GOTO {location.x} {location.y}"
                            ))
                            self._help_assignments[location] = AgentID(i + 1, 1)
                            break

        elif msg_type == "GOTO":
            self._current_goal = create_location(int(parts[1]), int(parts[2]))

        elif msg_type == "LEADER":
            self._leader_id = int(parts[1])
            self._is_leader = self._leader_id == self._agent.get_agent_id().id

    @override
    # Main logic that runs every round for the agent.
# Handles survivor saving, rubble digging, energy management, and coordination.
def think(self) -> None:
        self._agent.log("Thinking...")
        world = self.get_world()

        if self._agent.get_round_number() == 1:
            loc = self._agent.get_location()
            msg = f"INIT {self._agent.get_agent_id().id} {loc.x} {loc.y}"
            self._agent.send(SEND_MESSAGE(AgentIDList(), msg))

        if not world:
            return self.send_and_end_turn(MOVE(Direction.CENTER))

        curr_loc = self._agent.get_location()
        curr_cell = world.get_cell_at(curr_loc)

        if curr_cell is None:
            return self.send_and_end_turn(MOVE(Direction.CENTER))

        top_layer = curr_cell.get_top_layer()

        if isinstance(top_layer, Survivor):
            self._locs_with_survs_and_amount.pop(curr_loc, None)
            return self.send_and_end_turn(SAVE_SURV())

        if isinstance(top_layer, Rubble) and curr_cell.has_survivors:
            msg = f"HELP {self._agent.get_agent_id().id} {curr_loc.x} {curr_loc.y}"
            self._agent.send(SEND_MESSAGE(AgentIDList([AgentID(self._leader_id, 1)]), msg))
            return self.send_and_end_turn(TEAM_DIG())

        if self._current_goal:
            path = self.get_path_to_location(world, self._current_goal)
            if path:
                return self.make_a_move(path[0])

        target_survivor = self.get_closest_survivor()
        if target_survivor:
            path_tuple = self.get_path_to_location(world, target_survivor)
            if path_tuple:
                path, path_cost = path_tuple
                if (path_cost + 1) > self._agent.get_energy_level():
                    if curr_cell.is_charging_cell():
                        return self.send_and_end_turn(SLEEP())
                    charging_cell = self.get_closest_charging_cell(world, path)
                    if charging_cell:
                        charging_path = self.get_path_to_location(world, charging_cell)
                        if charging_path:
                            return self.make_a_move(charging_path[0])
                return self.make_a_move(path[0])

        return self.send_and_end_turn(MOVE(Direction.CENTER))

    def send_and_end_turn(self, command: AgentCommand):
        self._agent.log(f"SENDING {command}")
        self._agent.send(command)
        self._agent.send(END_TURN())

    def make_a_move(self, next_loc: Location):
        direction = self._agent.get_location().direction_to(next_loc)
        self.send_and_end_turn(MOVE(direction))

    # Scans the world grid to find all cells with survivors.
# Populates the _locs_with_survs_and_amount dictionary.
def get_survivor_locations(self, world):
        grid = world.get_world_grid()
        for row in grid:
            for cell in row:
                if cell.has_survivors:
                    self._locs_with_survs_and_amount[cell.location] = 1
        return list(self._locs_with_survs_and_amount.keys())

    def get_closest_survivor(self):
        self.get_survivor_locations(self.get_world())
        survivor_locations = list(self._locs_with_survs_and_amount.keys())
        if not survivor_locations:
            return None
        min_dist = float('inf')
        closest_survivor = None
        for loc in survivor_locations:
            dist = self.get_heuristic(self._agent.get_location(), loc)
            if dist < min_dist:
                min_dist = dist
                closest_survivor = loc
        return closest_survivor

    # Uses A* algorithm to find the shortest path to the target location.
# Returns the path and its movement cost.
def get_path_to_location(self, world, target):
        if target is None:
            return None
        found = [[False for _ in range(world.width)] for _ in range(world.height)]
        to_visit = [(0, [self._agent.get_location()])]
        while to_visit:
            current_cost, current_path = heappop(to_visit)
            current_location = current_path[-1]
            if current_location is not self._agent.get_location():
                current_cost -= self.get_heuristic(current_location, target)
            if current_location == target:
                return (current_path[1:], current_cost)
            for direction in Direction:
                if direction != Direction.CENTER:
                    adj_location = current_location.add(direction)
                    if adj_location and world.on_map(adj_location) and not found[adj_location.y][adj_location.x]:
                        found[adj_location.y][adj_location.x] = True
                        cell = world.get_cell_at(adj_location)
                        if cell.is_normal_cell() or cell.is_charging_cell():
                            heuristic = self.get_heuristic(adj_location, target)
                            heappush(to_visit, (current_cost + cell.move_cost + heuristic, current_path + [adj_location]))
        return None

    def get_heuristic(self, current_loc, target):
        dx = abs(target.x - current_loc.x)
        dy = abs(target.y - current_loc.y)
        return max(dx, dy)

    def get_charging_locations(self, world):
        charging_locations = []
        grid = world.get_world_grid()
        for row in grid:
            for cell in row:
                if cell.is_charging_cell():
                    charging_locations.append(cell.location)
        return charging_locations

    # Finds the charging cell closest to the current path.
# Used when agent doesn't have enough energy to complete its task.
def get_closest_charging_cell(self, world, path):
        charging_locations = self.get_charging_locations(world)
        if not charging_locations or not path:
            return None
        min_dist = float('inf')
        closest_loc = None
        for charge_loc in charging_locations:
            for path_loc in path:
                dist = self.get_heuristic(charge_loc, path_loc)
                if dist < min_dist:
                    min_dist = dist
                    closest_loc = charge_loc
        return closest_loc
