from typing import override

# If you need to import anything else, add it to the import below.
from aegis import (
    END_TURN,
    MOVE,
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
        # Some potentially useful suggestions:
        # self._locs_with_survs_and_amount: dict[Location, int] = {}
        # self._visited_locations: set[Location] = set()
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
            self.send_and_end_turn(SAVE_SURV())
            # return is used after EVERY send_and_end_turn method call to "end turn early". This is so only 1 command is sent to aegis, meaning only 1 command is processed.
            # If 2+ commands are sent, only the last will be processed, leading to potentially unexpected behaviour from your agent(s).
            return

        # If rubble is present, try to clear it and end the turn.
        if isinstance(top_layer, Rubble):
            self.send_and_end_turn(TEAM_DIG())
            return

        # Additional logic can be added here (or anywhere), such as choosing which direction to move to based on lots of different factors!
        # You can make decisions using data you have learned through messages and stored in your data structures above
        # e.g. if you are the leader, you can find the closest agent to a survivor and tell that agent to go save them

        # Generate a path to the survivor
        #TODO: Current algorithm works for just 1 survivor, change it so it works for multiple survivors (to be done by Mahin)
        path = self.get_path_to_survivor(world)

        # Make a move according to the path
        self.make_a_move(path)

    def send_and_end_turn(self, command: AgentCommand):
        """Send a command and end your turn."""
        self._agent.log(f"SENDING {command}")
        self._agent.send(command)
        self._agent.send(END_TURN())

    def get_survivor_location(self, world):
        grid = world.get_world_grid()  # grid is a list[list[Cell]]
        for row in grid:
            for cell in row:
                if cell.has_survivors:
                    return cell.location
        return None

    # Method for pathfinding. Returns a list of locations making up the path; Returns None if no path found
    def get_path_to_survivor(self, world):

        # Locate the survivor, if no survivor found then return None
        survivor_location = self.get_survivor_location(world)
        if survivor_location is None:
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
                current_cost = current_cost - self.get_heuristic(current_location)

            # Check if survivor is at current location
            if current_location == survivor_location:
                return current_path[1:]  # We exclude 1st element since it is the spawn location

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
                            heuristic = self.get_heuristic(adj_location)
                            heappush(to_visit,
                                     (current_cost + cell.move_cost + heuristic, current_path + [adj_location]))
        return None

    # Move towards the survivor according to the path
    def make_a_move(self, path):
        # First check if path list is not empty
        if path:
            # Get the direction we need to move from our current location according to the path
            direction = self._agent.get_location().direction_to(path[0])
            path[1:]
            self.send_and_end_turn(MOVE(direction))

    # A method to calculate the heuristic for a given location
    def get_heuristic(self, loc):
        # Calculate the difference between x coordinates of survivor location and the given parameter location
        # Do the same for y coordinates
        x1 = self.get_survivor_location(self.get_world()).x
        x2 = loc.x
        y1 = self.get_survivor_location(self.get_world()).y
        y2 = loc.y
        dx = abs(x1 - x2)
        dy = abs(y1 - y2)

        # Return the higher difference out of x coordinates and y coordinates
        if dx > dy:
            return dx
        return dy

        # Logic: Since we can move diagonally, we can move horizontally and vertically at the same time. Thus,
        # we need maximum dx or dy steps, whichever is greater, because we can cover both directions in that amount
        # of steps. Now since the minimum move cost of cells is 1, total cost of path is always greater than or equal
        # to the total steps. Hence, the heuristic is admissible.
