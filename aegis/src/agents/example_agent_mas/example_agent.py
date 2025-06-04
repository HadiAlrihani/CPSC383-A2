from typing import override

# If you need to import anything else, add it to the import below.
from aegis import (
    END_TURN,
    MOVE,
    SLEEP,
    SAVE_SURV,
    SEND_MESSAGE,
    SEND_MESSAGE_RESULT,
    TEAM_DIG,
    AgentCommand,
    AgentIDList,
    AgentID,
    World,
    Cell,
    Direction,
    Rubble,
    Survivor,
    Location,
    create_location,
)
from mas.agent import BaseAgent, Brain, AgentController
from heapq import heappush, heappop


class ExampleAgent(Brain):
    # Store any constants you want to define here
    # Example:
    NUM_AGENTS = 7

    def __init__(self) -> None:
        super().__init__()
        self._agent: AgentController = BaseAgent.get_agent()

        # Initalize any variables or data structures here
        self._locs_with_survs_and_amount: dict[Location, int] = {}  # amount is the number of agents needed to save a survivor (i.e. to remove rubble)
        self._visited_locations: set[Location] = set()
        self._agent_locations: list[Location | None] = [None] * self.NUM_AGENTS
        self._current_goal: Location | None = None

    @override
    def handle_send_message_result(self, smr: SEND_MESSAGE_RESULT) -> None:
        # This runs whenever a message is received by this agent. Messages are received one round after they are sent.
        # Figure out some way to identify what the message is about/what info it contains, and process it accordingly.
        # smr.msg stores the string containing the message

        self._agent.log(f"SEND_MESSAGE_RESULT: {smr}")

        # Below is an example of how you could structure your message handling.
        # For this approach, your message consists of a message type string followed by numeric information (e.g. coordinates)
        # Different parts of the message are split by spaces so we can easily separate them

        # Example message: receiving "MOVE 2 1" tells this agent to move to Location (2, 1)

        # We can start by splitting the message components into a list of strings based on spaces
        msg_list = smr.msg.split()

        if msg_list[0] == "MOVE":
            # Agent receiving this message should move to the specified location as its next movement
            # Format: MOVE {x coordinate} {y coordinate}
            location_x = int(msg_list[1])
            location_y = int(msg_list[2])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            self._current_goal = location

            # Log the received message and the agent's location.
            self._agent.log(f"Agent {self._agent.get_agent_id().id} is heading to location: {location}")

        elif msg_list[0] == "INIT":
            # Initialization message where agents send their starting location along with their ID
            # Format: INIT {agent_id} {x coordinate} {y coordinate}
            agent_id = int(msg_list[1])
            location_x = int(msg_list[2])
            location_y = int(msg_list[3])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            self._agent_locations[agent_id - 1] = location

        elif msg_list[0] == "HELP":
            # Message where agents ask for help removing rubble, sent to leader agent
            # Necessary since rubble cannot be detected until an agent is adjacent to it
            # Format: HELP {agent_id of agent requesting help} {x coordinate} {y coordinate}
            agent_id = int(msg_list[1]) #used so we don't accidentally consider sending the agent requesting for help as the helper
            location_x = int(msg_list[2])
            location_y = int(msg_list[3])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            #Determine which agent should be sent as the helper

        elif msg_list[0] == "GOTO":
            # Message from group leader ordering an agent to help another agent remove rubble
            # Format: GOTO {x coordinate of rubble} {y coordinate of rubble}
            location_x = int(msg_list[1])
            location_y = int(msg_list[2])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            #Agent receiving this message should begin to move towards the location in the rubble

        elif msg_list[0] == "LEADER":
            # Message sharing the id of the agent leader
            # Format: LEADER {agent id}
            leader_id = msg_list[1]

        else:
            # A message was sent that doesn't match any of our known formats
            self._agent.log(f"Unknown message format: {smr.msg}")

    @override
    def think(self) -> None:
        self._agent.log("Thinking")

        # Examples of how to send a message to other agents.

        #TODO: Make agent with id 1 as the leader. Keep a variable so that if leader dies then the agent with next id becomes leader. Can also keep a boolean is_leader to know if current agent is leader.

        # Using AgentIDList() will send the message to all agents in your group
        # Useful for broadcasting information, such as about the world state (e.g. to tell people a survivor was saved) or needing help with a task (e.g. need another agent to help dig this rubble)).
        self._agent.send(SEND_MESSAGE(AgentIDList(), f"Hello from agent {self._agent.get_agent_id().id}!"))

        # Putting in a specific agent ID will send to that agent only (e.g. sending information to a group leader).
        # Here we are telling agent 2 to move to our current location if we are the leader (ID = 1)
        if self._agent.get_agent_id().id == 1:
            message = f"MOVE {self._agent.get_location().x} {self._agent.get_location().y}"
            self._agent.send(SEND_MESSAGE(AgentIDList([AgentID(2, 1)]), message))

        # Retrieve the current state of the world.
        world = self.get_world()
        if world is None:
            self.send_and_end_turn(MOVE(Direction.CENTER))
            return

        # Fetch the cell at the agent’s current location. If the location is outside the world’s bounds,
        # return a default move action and end the turn.
        current_cell = world.get_cell_at(self._agent.get_location())
        if current_cell is None:
            self.send_and_end_turn(MOVE(Direction.CENTER))
            return

        # Get the top layer at the agent’s current location.
        top_layer = current_cell.get_top_layer()

        # If a survivor is present, save it and end the turn.
        if isinstance(top_layer, Survivor):
            # Remove survivor from dictionary since they are being saved
            self._locs_with_survs_and_amount.pop(current_cell.location, None)
            self.send_and_end_turn(SAVE_SURV())
            # return is used after EVERY send_and_end_turn method call to "end turn early". This is so only 1 command is sent to aegis, meaning only 1 command is processed.
            # If 2+ commands are sent, only the last will be processed, leading to potentially unexpected behaviour from your agent(s).
            return

        # If rubble is present and survivor is present, try to clear it and end the turn.
        if isinstance(top_layer, Rubble) and world.get_cell_at(self._agent.get_location()).has_survivors:
            self.send_and_end_turn(TEAM_DIG())
            return

        # Additional logic can be added here (or anywhere), such as choosing which direction to move to based on lots of different factors!
        # You can make decisions using data you have learned through messages and stored in your data structures above
        # e.g. if you are the leader, you can find the closest agent to a survivor and tell that agent to go save them

        # Generate a path to the survivor

        target_survivor = self.get_closest_survivor()

        # If a target survivor exists, move towards it
        if target_survivor:
            path_tuple = self.get_path_to_location(world, target_survivor)  # The tuple contains both that path and cost

            # If path to survivor does not exist, remove the survivor from our dictionary
            if not path_tuple:
                self._locs_with_survs_and_amount.pop(target_survivor, None)
                self.send_and_end_turn(MOVE(Direction.CENTER))
                return

            # The path tuple contains both that path and cost
            path, path_cost = path_tuple

            # If agent does not have enough energy to reach survivor and save it, then find the closest charging cell
            if (path_cost + 1) > self._agent.get_energy_level():  # +1 is added which is saving cost

                # If current location has a charge cell, use it. Else, find the charge cell
                if world.get_cell_at(self._agent.get_location()).is_charging_cell():
                    self.send_and_end_turn(SLEEP())
                else:
                    charging_cell = self.get_closest_charging_cell(world, path)
                    if charging_cell:
                        charging_path, charging_path_cost = self.get_path_to_location(world, charging_cell)
                        self.make_a_move(charging_path)
                        return
            # Make a move according to the path
            self.make_a_move(path)
            return

    def send_and_end_turn(self, command: AgentCommand):
        """Send a command and end your turn."""
        self._agent.log(f"SENDING {command}")
        self._agent.send(command)
        self._agent.send(END_TURN())

    # This method returns a list of all survivors in the world and adds them to self._locs_with_survs_and_amount dictionary
    def get_survivor_locations(self, world):
        grid = world.get_world_grid()  # grid is a list[list[Cell]]
        for row in grid:
            for cell in row:
                if cell.has_survivors:
                    self._locs_with_survs_and_amount[cell.location] = 1

        return list(self._locs_with_survs_and_amount.keys())

    # This method returns the location of a survivor which is closest to the current agent (based on heuristic)
    # Parameter is a list of all survivors
    def get_closest_survivor(self,):
        self.get_survivor_locations(self.get_world())  # Updates self._locs_with_survs_and_amount
        survivor_locations = list(self._locs_with_survs_and_amount.keys())

        # If no survivors left, return None
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

    #TODO: Issues: Survivor is already being saved by another agent (Might need multiple agents for clearing ruble)

    # Method for pathfinding. Returns a list of locations making up the path and cost of path; None if no path found
    def get_path_to_location(self, world, target):

        if target is None:
            return None

        # Create a 2d list to mark visited/found cells during pathfinding
        found = [[False for _ in range(world.width)] for _ in range(world.height)]  # Initially no cells are found

        to_visit = []  # A priority queue to store the paths we want to visit
        # We start the path with the agent location; The move cost of the initial agent location is 0
        heappush(to_visit, (0, [self._agent.get_location()]))

        while len(to_visit) > 0:
            current_cost, current_path = heappop(to_visit)
            current_location = current_path[-1]

            # Subtract the heuristic value from current cost
            if current_location is not self._agent.get_location():
                current_cost = current_cost - self.get_heuristic(current_location, target)

            # Check if our target is our current location
            if current_location == target:
                return (current_path[1:], current_cost)  # We exclude 1st element since it is the spawn location

            # Iterate through the neighbours of the current cell
            for direction in Direction:
                if direction != Direction.CENTER:
                    adj_location = current_location.add(direction)

                    # Check if the location is valid (can't be -ve), on the map and not already found
                    if adj_location is not None and world.on_map(adj_location) and not found[adj_location.y][adj_location.x]:
                        found[adj_location.y][adj_location.x] = True
                        cell = world.get_cell_at(adj_location)

                        # Only visit if normal or charging cell
                        if cell.is_normal_cell() or cell.is_charging_cell():
                            # Calculate heuristic for the cell at the location we are searching
                            heuristic = self.get_heuristic(adj_location, target)
                            heappush(to_visit,
                                     (current_cost + cell.move_cost + heuristic, current_path + [adj_location]))
        return None

    # Move towards the survivor according to the path
    def make_a_move(self, path):
        # First check if path list is not empty
        if path:
            # Get the direction we need to move from our current location according to the path
            direction = self._agent.get_location().direction_to(path[0])
            self.send_and_end_turn(MOVE(direction))
            return
        # Default move is to stay at the same location
        self.send_and_end_turn(MOVE(Direction.CENTER))
        return

    # A method to calculate the heuristic for a given location from a target
    def get_heuristic(self, current_loc, target):
        # Calculate the difference between x coordinates of survivor location and the given parameter location
        # Do the same for y coordinates
        x1 = target.x
        x2 = current_loc.x
        y1 = target.y
        y2 = current_loc.y
        dx = abs(x1 - x2)
        dy = abs(y1 - y2)

        # Return the higher difference out of x coordinates and y coordinates
        if dx > dy:
            return dx
        return dy

    # This method returns a list of all survivors in the world and adds them to self._locs_with_survs_and_amount dictionary
    def get_charging_locations(self, world):
        charging_locations = []
        grid = world.get_world_grid()  # grid is a list[list[Cell]]
        for row in grid:
            for cell in row:
                if cell.is_charging_cell():
                    charging_locations.append(cell.location)
        return charging_locations

    # Method to find the closest charging location/cell to the path we are following
    # Parameters are the world object and path to the survivor
    def get_closest_charging_cell(self, world, path):
        charging_locations = self.get_charging_locations(world)

        # If charging locations or a path to the survivors does not exist, return None
        if not charging_locations or not path:
            return None

        # Find the closest charge location by comparing heuristic distance with all the locations in our path
        min_dist = float('inf')
        closest_loc = None
        for charge_loc in charging_locations:
            for path_loc in path:
                dist = self.get_heuristic(charge_loc, path_loc)
                if dist < min_dist:
                    min_dist = dist
                    closest_loc = charge_loc
        return closest_loc
