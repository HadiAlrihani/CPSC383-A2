from typing import override
from aegis import (
    END_TURN, MOVE, SLEEP, SAVE_SURV, SEND_MESSAGE, SEND_MESSAGE_RESULT,
    TEAM_DIG, AgentCommand, AgentIDList, AgentID, World, Cell, Direction,
    Rubble, Survivor, Location, create_location
)
from mas.agent import BaseAgent, Brain, AgentController
from heapq import heappush, heappop


class ExampleAgent(Brain):
    NUM_AGENTS = 7

    def __init__(self) -> None:
        super().__init__()
        self._agent: AgentController = BaseAgent.get_agent()
        self._survivors: dict[Location, int] = {}
        self._visited: set[Location] = set()
        self._agent_positions: list[Location | None] = [None] * self.NUM_AGENTS
        self._goal: Location | None = None
        self._is_leader: bool = False
        self._leader_id: int = 1

    @override
    def handle_send_message_result(self, smr: SEND_MESSAGE_RESULT) -> None:
        """Process messages received from other agents."""
        self._agent.log(f"Received message: {smr.msg}")
        parts = smr.msg.strip().split()
        if not parts:
            return

        msg_type = parts[0]

        if msg_type == "MOVE":
            self._goal = create_location(int(parts[1]), int(parts[2]))

        elif msg_type == "INIT":
            aid = int(parts[1])
            self._agent_positions[aid - 1] = create_location(int(parts[2]), int(parts[3]))

        elif msg_type == "HELP":
            # Format: HELP agent_id x y
            pass  # Can implement logic to choose helper here

        elif msg_type == "GOTO":
            self._goal = create_location(int(parts[1]), int(parts[2]))

        elif msg_type == "LEADER":
            self._leader_id = int(parts[1])
            self._is_leader = self._leader_id == self._agent.get_agent_id().id

        else:
            self._agent.log(f"Unknown message: {smr.msg}")

    @override
    def think(self) -> None:
        """Main agent logic per round."""
        self._agent.log("Agent thinking...")

        # Broadcast starting location on round 1
        if self._agent.get_round_number() == 1:
            loc = self._agent.get_location()
            msg = f"INIT {self._agent.get_agent_id().id} {loc.x} {loc.y}"
            self._agent.send(SEND_MESSAGE(AgentIDList(), msg))

        world = self.get_world()
        if not world:
            return self._act(MOVE(Direction.CENTER))

        curr_loc = self._agent.get_location()
        curr_cell = world.get_cell_at(curr_loc)
        if not curr_cell:
            return self._act(MOVE(Direction.CENTER))

        # Handle saving survivor
        if isinstance(curr_cell.get_top_layer(), Survivor):
            self._survivors.pop(curr_loc, None)
            return self._act(SAVE_SURV())

        # Dig if rubble + survivor present
        if isinstance(curr_cell.get_top_layer(), Rubble) and curr_cell.has_survivors:
            return self._act(TEAM_DIG())

        # Leader logic: assign other agents
        if self._is_leader:
            # Example: send MOVE command to agent 2
            self._agent.send(SEND_MESSAGE(AgentIDList([AgentID(2, 1)]), f"MOVE {curr_loc.x} {curr_loc.y}"))

        # Find closest survivor
        target = self._closest_survivor()
        if target:
            path_cost_pair = self._find_path(world, target)
            if not path_cost_pair:
                self._survivors.pop(target, None)
                return self._act(MOVE(Direction.CENTER))

            path, cost = path_cost_pair
            energy = self._agent.get_energy_level()

            if (cost + 1) > energy:
                if curr_cell.is_charging_cell():
                    return self._act(SLEEP())

                charge_target = self._closest_charge_to_path(world, path)
                if charge_target:
                    charge_path, _ = self._find_path(world, charge_target)
                    return self._move_along(charge_path)

            return self._move_along(path)

        return self._act(MOVE(Direction.CENTER))

    def _act(self, cmd: AgentCommand):
        self._agent.log(f"Executing: {cmd}")
        self._agent.send(cmd)
        self._agent.send(END_TURN())

    def _move_along(self, path: list[Location]):
        if path:
            direction = self._agent.get_location().direction_to(path[0])
            self._act(MOVE(direction))
        else:
            self._act(MOVE(Direction.CENTER))

    def _closest_survivor(self) -> Location | None:
        """Return the closest survivor location based on heuristic."""
        self._update_survivor_cache()
        if not self._survivors:
            return None
        return min(self._survivors, key=lambda loc: self._heuristic(self._agent.get_location(), loc))

    def _update_survivor_cache(self):
        world = self.get_world()
        if not world:
            return
        for row in world.get_world_grid():
            for cell in row:
                if cell.has_survivors:
                    self._survivors[cell.location] = 1

    def _find_path(self, world: World, target: Location) -> tuple[list[Location], int] | None:
        """A* search to find path to target."""
        visited = [[False] * world.width for _ in range(world.height)]
        start = self._agent.get_location()
        heap = [(0, [start])]

        while heap:
            cost, path = heappop(heap)
            curr = path[-1]

            if curr == target:
                return path[1:], cost

            for direction in Direction:
                if direction == Direction.CENTER:
                    continue

                neighbor = curr.add(direction)
                if not world.on_map(neighbor):
                    continue

                if visited[neighbor.y][neighbor.x]:
                    continue

                cell = world.get_cell_at(neighbor)
                if not (cell.is_normal_cell() or cell.is_charging_cell()):
                    continue

                visited[neighbor.y][neighbor.x] = True
                heuristic = self._heuristic(neighbor, target)
                heappush(heap, (cost + cell.move_cost + heuristic, path + [neighbor]))

        return None

    def _heuristic(self, a: Location, b: Location) -> int:
        return max(abs(a.x - b.x), abs(a.y - b.y))

    def _charging_cells(self, world: World) -> list[Location]:
        return [cell.location for row in world.get_world_grid() for cell in row if cell.is_charging_cell()]

    def _closest_charge_to_path(self, world: World, path: list[Location]) -> Location | None:
        charging = self._charging_cells(world)
        if not charging:
            return None

        return min(
            charging,
            key=lambda ch: min(self._heuristic(ch, step) for step in path),
            default=None
        )
