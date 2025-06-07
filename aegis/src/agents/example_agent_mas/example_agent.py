'''
Name: Hadi Alrihani, Hasan Qasim, Mahin Chondigara
Date: June 6, 2025
Course: CPSC 383
Semester: Spring 2025
Tutorial: T02 (Hadi, Mahin), T01 (Hasan)
'''

from typing import override, Optional

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

    def __init__(self) -> None:
        super().__init__()
        self._agent: AgentController = BaseAgent.get_agent()

        # Initalize any variables or data structures here
        self._locs_with_survs_and_amount: dict[Location, int] = {}  # amount is the number of agents needed to save a survivor (i.e. to remove rubble)
        self._status_of_survivor: dict[Location, tuple[bool, int]] = {}  # Boolean value is True if an agent is on its way to save the survivor, False otherwise. Int value is agent id saving it.
        self._agent_locations_and_energy: dict[int, tuple[Location, int]] = {}  # Key is agent id (just the int unique id), Value is a tuple of location and energy
        self._agent_location_of_helping: dict[int, Optional[Location]] = {}  # Key is agent id (just uid), Value is a tuple of location its helping at (None if not helping)
        self._following_agent: dict[int, Optional[int]] = {}  # Key is id of agent following, value is id of agent being followed
        self._current_goal: Location | None = None

    @override
    def handle_send_message_result(self, smr: SEND_MESSAGE_RESULT) -> None:
        # This runs whenever a message is received by this agent. Messages are received one round after they are sent.
        # Figure out some way to identify what the message is about/what info it contains, and process it accordingly.
        # smr.msg stores the string containing the message

        self._agent.log(f"SEND_MESSAGE_RESULT: {smr}")

        # MESSAGE HANDLING
        # For this approach, your message consists of a message type string followed by numeric information (e.g. coordinates)
        # Different parts of the message are split by spaces so we can easily separate them

        # We can start by splitting the message components into a list of strings based on spaces
        msg_list = smr.msg.split()

        if msg_list[0] == "LOC":
            # Message where agents send the location they will be at in the next round
            # Also their energy after next round
            # Format: LOC {x coordinate} {y coordinate}
            location_x = int(msg_list[1])
            location_y = int(msg_list[2])
            energy = int(msg_list[3])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            self._agent_locations_and_energy[smr.from_agent_id.id] = (location, energy)

        elif msg_list[0] == "HELP":
            # Message where agents ask for help removing rubble
            # Necessary since rubble cannot be detected until an agent is adjacent to it
            # Format: HELP {agent_id of agent whose help we want} {x coordinate of rubble} {y coordinate of rubble}
            agent_id = int(msg_list[1])
            location_x = int(msg_list[2])
            location_y = int(msg_list[3])
            # Create a Location object from the extracted coordinates.
            location = create_location(location_x, location_y)

            # Update helping location and status of the agent whose help is needed
            self._agent_location_of_helping[agent_id] = location

        elif msg_list[0] == "HELP_OVER":
            # Message where agents tell their help is over, so other agents can ask them for another help if needed
            # Format: HELP_OVER
            agent_id = smr.from_agent_id.id

            self._agent_location_of_helping[agent_id] = None

        elif msg_list[0] == "FOLLOWING":
            # Message where agents select another agent to follow
            # Format: FOLLOWING {ID of agent we are following}
            target_id = int(msg_list[1])
            follower_agent  = smr.from_agent_id.id

            self._following_agent[follower_agent] = target_id

        elif msg_list[0] == "FOLLOWING_STOPPED":
            # Message where agents tell they stopped following, so other agents can ask them for another help if needed
            # Format: FOLLOWING_STOPPED
            agent_id = smr.from_agent_id.id

            self._following_agent[agent_id] = None

        elif msg_list[0] == "CANCELED_TASKS":
            # Message where agents tell they are not saving a survivor if they initially were going to
            # So other agents can take over their tasks if possible
            # Format: CANCELED_TASKS
            agent_id = smr.from_agent_id.id

            self.cancel_tasks(agent_id)

        elif msg_list[0] == "SAVING":
            # Message from an agent which is saving a survivor at the mentioned location
            # So that we don't save the save survivor if help is not needed
            # Format: SAVING {x coordinate} {y coordinate}
            location_x = int(msg_list[1])
            location_y = int(msg_list[2])
            # Update it in our status_of_survivor dictionary
            self._status_of_survivor[create_location(location_x, location_y)] = (True, smr.from_agent_id.id)

        else:
            # A message was sent that doesn't match any of our known formats
            self._agent.log(f"Unknown message format: {smr.msg}")

    @override
    def think(self) -> None:
        self._agent.log("Thinking")

        if self._agent.get_round_number() == 1:
            # Locate all survivors and set their status. Will be helpful in knowing which survivor is being saved.
            grid = self.get_world().get_world_grid()  # grid is a list[list[Cell]]
            for row in grid:
                for cell in row:
                    if cell.has_survivors:
                        self._status_of_survivor[cell.location] = (False, 0) # Agent ID is set as zero since no agent is saving the survivor

            # Set helping location to None (not helping)
            self._agent_location_of_helping[self._agent.get_agent_id().id] = None
            self._agent.send(SEND_MESSAGE(AgentIDList(), f"HELP_OVER"))

        # Set following agent to None (not following) at start of each round, so if we don't need to follow then other agents can follow
        self._following_agent[self._agent.get_agent_id().id] = None
        self._agent.send(SEND_MESSAGE(AgentIDList(), f"FOLLOWING_STOPPED"))

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
            self._status_of_survivor[current_cell.location] = (False, 0)  # Set status to false cause the survivor is saved and there might be another survivor at that location who might need saving

            # Search for new survivors since this one is saved
            new_surv_loc = self.get_takeover_survivor(world)
            # If we selected a survivor mark it as being saved and inform the other agents
            if new_surv_loc:
                self._status_of_survivor[new_surv_loc] = (True, self._agent.get_agent_id().id)
                self._agent.send(SEND_MESSAGE(AgentIDList(), f"SAVING {new_surv_loc.x} {new_surv_loc.y}"))

            self.send_and_end_turn(SAVE_SURV())
            # return is used after EVERY send_and_end_turn method call to "end turn early". This is so only 1 command is sent to aegis, meaning only 1 command is processed.
            # If 2+ commands are sent, only the last will be processed, leading to potentially unexpected behaviour from your agent(s).
            return

        # If rubble is present and survivor is present, try to clear it and end the turn.
        if isinstance(top_layer, Rubble) and world.get_cell_at(self._agent.get_location()).has_survivors:
            # Check how many agents needed and energy needed for removing
            agents_needed = top_layer.remove_agents
            energy_needed = top_layer.remove_energy
            agents_present = len(self.get_agents_at_location(self._agent.get_location()))
            num_of_more_agents_needed = agents_needed - agents_present

            # Call agents for help if needed
            if num_of_more_agents_needed > 0:
                # Call only the number of agents that are needed
                list_of_selected_agents = self.get_closest_available_agent_for_rubble(world, self._agent.get_location(), energy_needed, num_of_more_agents_needed)
                # Send message requesting help from selected agents, if it has not started helping already
                for id in list_of_selected_agents:
                    if not self._agent_location_of_helping[id] == self._agent.get_location():
                        self._agent.send(SEND_MESSAGE(AgentIDList(), f"HELP {id} {self._agent.get_location().x} {self._agent.get_location().y}"))
                self.send_and_end_turn(SLEEP())
                return
            else:
                # If current agent is done helping, send a message saying it's done
                if self._agent_location_of_helping[self._agent.get_agent_id().id]:
                    self._agent_location_of_helping[self._agent.get_agent_id().id] = None
                    self._agent.send(SEND_MESSAGE(AgentIDList(), f"HELP_OVER"))
                self.send_and_end_turn(TEAM_DIG())
                return

        # If this agent's help is needed, go to the rubble and cancel current tasks if any
        if self._agent_location_of_helping[self._agent.get_agent_id().id]:
            self.cancel_tasks(self._agent.get_agent_id().id)
            # Send a message to other tasks that this agent has cancelled its other tasks
            self._agent.send(SEND_MESSAGE(AgentIDList(), f"CANCELED_TASKS"))

            # Move to the rubble
            self._current_goal = self._agent_location_of_helping[self._agent.get_agent_id().id]
            path, path_cost = self.get_path_to_location(world, self._agent.get_location(), self._current_goal)
            # Make a move according to the path
            # Send your next location and energy to all the agents (next location helps with message lag of 1 round)
            next_loc = path[0]
            move_cost = world.get_cell_at(next_loc).move_cost
            self._agent.send(SEND_MESSAGE(AgentIDList(),f"LOC {next_loc.x} {next_loc.y} {self._agent.get_energy_level() - move_cost}"))
            self.make_a_move(path)
            return


        # Printing locations of agents and status of survivors for debugging
        self._agent.log(f"LOCATIONS: {self._agent_locations_and_energy}")
        self._agent.log(f"SAVING: {self._status_of_survivor}")

        # GENERATE A PATH TO THE SURVIVOR
        # Start by finding the closest survivor to save
        self._current_goal = self.get_closest_survivor()

        # If a goal exists, move towards it, else end turn
        if self._current_goal:
            path_tuple = self.get_path_to_location(world, self._agent.get_location(), self._current_goal)  # The tuple contains both, the path and cost

            # The path tuple contains both that path and cost
            path, path_cost = path_tuple
            # Mark survivor as being saved, if not already marked
            if not self._status_of_survivor[self._current_goal][0]:
                self._status_of_survivor[self._current_goal] = (True, self._agent.get_agent_id().id)
                # Send a message to other agents that current agent is saving a survivor at what location
                self._agent.send(SEND_MESSAGE(AgentIDList(), f"SAVING {self._current_goal.x} {self._current_goal.y}"))

            # If agent does not have enough energy to reach survivor and save it, then find the closest charging cell
            if (path_cost + 1) > self._agent.get_energy_level():  # +1 is added which is saving cost

                # If current location has a charge cell, use it. Else, find and move to the charge cell
                if world.get_cell_at(self._agent.get_location()).is_charging_cell():
                    self.send_and_end_turn(SLEEP())
                else:
                    charging_cell = self.get_closest_charging_cell(world, path)
                    if charging_cell:
                        charging_path, charging_path_cost = self.get_path_to_location(world, self._agent.get_location(), charging_cell)
                        # Send your next location and energy to all the agents (next location helps with message lag of 1 round)
                        next_loc = charging_path[0]
                        move_cost = world.get_cell_at(next_loc).move_cost
                        self._agent.send(SEND_MESSAGE(AgentIDList(), f"LOC {next_loc.x} {next_loc.y} {self._agent.get_energy_level() - move_cost}"))
                        self.make_a_move(charging_path)
                        return
            # Make a move according to the path
            # Send your next location and energy to all the agents (next location helps with message lag of 1 round)
            next_loc = path[0]
            move_cost = world.get_cell_at(next_loc).move_cost
            self._agent.send(SEND_MESSAGE(AgentIDList(), f"LOC {next_loc.x} {next_loc.y} {self._agent.get_energy_level() - move_cost}"))
            self.make_a_move(path)
            return
        else:
            # Since this agent does not have a task, follow another agent in case they need help later
            target_agent_id = self.get_agent_to_follow(world)
            if target_agent_id:
                self._current_goal = self._agent_locations_and_energy[target_agent_id][0]
                # Inform other agents that we are following someone
                self._agent.send(SEND_MESSAGE(AgentIDList(),f"FOLLOWING {target_agent_id}"))
                path, path_cost = self.get_path_to_location(world, self._agent.get_location(), self._current_goal)
                if path:
                    # Send your next location and energy to all the agents (next location helps with message lag of 1 round)
                    next_loc = path[0]
                    move_cost = world.get_cell_at(next_loc).move_cost
                    self._agent.send(SEND_MESSAGE(AgentIDList(),f"LOC {next_loc.x} {next_loc.y} {self._agent.get_energy_level() - move_cost}"))
                self.make_a_move(path)
                return
            else:
                # Sending sleep does not use energy and agent doesn't move
                self.send_and_end_turn(SLEEP())
                return

    def send_and_end_turn(self, command: AgentCommand):
        """Send a command and end your turn."""
        self._agent.log(f"SENDING {command}")
        self._agent.send(command)
        self._agent.send(END_TURN())

    # This method returns a list of survivors in the world (not being saved) and adds them to self._locs_with_survs_and_amount dictionary
    def get_survivor_locations(self, world):
        self._locs_with_survs_and_amount.clear()
        grid = world.get_world_grid()  # grid is a list[list[Cell]]
        for row in grid:
            for cell in row:
                # Only add survivor if it is not being saved by another agent
                if cell.has_survivors and (not self._status_of_survivor[cell.location][0] or self._status_of_survivor[cell.location][1] == self._agent.get_agent_id().id):
                    # Only add survivor if it is reachable
                    path_tuple = self.get_path_to_location(world, self._agent.get_location(), cell.location)  # The tuple contains both, the path and cost
                    if not path_tuple:
                        self._status_of_survivor[self._current_goal] = (True, 0)  # Since we can't reach this survivor, we assume someone else is saving them and we ignore it
                    else:
                        self._locs_with_survs_and_amount[cell.location] = 1

        return list(self._locs_with_survs_and_amount.keys())

    # This method returns the location of a survivor which is closest to the current agent (based on heuristic)
    # Parameter is a list of all survivors
    def get_closest_survivor(self,):
        survivor_locations = self.get_survivor_locations(self.get_world())

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

    # Method for an agent to take over the role of saving a survivor from another agent (if possible to do it faster)
    def get_takeover_survivor(self, world):
        grid = world.get_world_grid()  # grid is a list[list[Cell]]
        total_survivors = []  # Include non-savable and those being saved.
        for row in grid:
            for cell in row:
                # Cannot be same location as agent as this survivor will be getting saved anyways.
                if cell.has_survivors and not cell.location == self._agent.get_location():
                    total_survivors.append(cell.location)

        # Select the survivor based on heuristic distance
        min_dist = float('inf')
        selected_survivor_loc = None
        for loc in total_survivors:
            path_tuple = self.get_path_to_location(world, self._agent.get_location(), loc)
            # If path exists...
            if path_tuple:
                path, path_cost = path_tuple
                if path_cost < self._agent.get_energy_level():
                    # If the survivor is already being saved, select the best agent by comparing heuristic. Else assign the survivor to current agent
                    if self._status_of_survivor[loc][0]:
                        agent_saving_already_id = self._status_of_survivor[loc][1]  # ID of agent already saving it.
                        agent_saving_already_loc = self._agent_locations_and_energy[agent_saving_already_id][0]
                        agent_saving_already_dist = self.get_heuristic(agent_saving_already_loc, loc)
                        this_agent_dist = self.get_heuristic(self._agent.get_location(), loc)
                        # If this agent is closer and the survivor is closest out of all survivors so far, set it as selected survivor and update min_dist
                        if this_agent_dist < agent_saving_already_dist:
                            if this_agent_dist < min_dist:
                                min_dist = this_agent_dist
                                selected_survivor_loc = loc
                    else:
                        this_agent_dist = self.get_heuristic(self._agent.get_location(), loc)
                        if this_agent_dist < min_dist:
                            min_dist = this_agent_dist
                            selected_survivor_loc = loc

        return selected_survivor_loc

    # Method for pathfinding. Returns a list of locations making up the path and cost of path; None if no path found
    def get_path_to_location(self, world, start_loc, target_loc):

        if target_loc is None:
            return None

        # Create a 2d list to mark visited/found cells during pathfinding
        found = [[False for _ in range(world.width)] for _ in range(world.height)]  # Initially no cells are found

        to_visit = []  # A priority queue to store the paths we want to visit
        # We start the path with the start_loc; The move cost of the initial location is 0
        heappush(to_visit, (0, [start_loc]))

        while len(to_visit) > 0:
            current_cost, current_path = heappop(to_visit)
            current_location = current_path[-1]

            # Subtract the heuristic value from current cost
            if current_location is not start_loc:
                current_cost = current_cost - self.get_heuristic(current_location, target_loc)

            # Check if our target is our current location
            if current_location == target_loc:
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
                            heuristic = self.get_heuristic(adj_location, target_loc)
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
        # Default is to move to center
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

    # This method returns a list of locations of all charge cells in the world map
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

        # If charging cells or a path to the survivors does not exist, return None
        if not charging_locations or not path:
            return None

        # Find the closest charge cell by comparing heuristic distance of all charge cells with all the locations in our path
        min_dist = float('inf')
        closest_loc = None
        for charge_loc in charging_locations:
            for path_loc in path:
                dist = self.get_heuristic(charge_loc, path_loc)
                if dist < min_dist:
                    min_dist = dist
                    closest_loc = charge_loc
        return closest_loc

    # Method that returns a list of agent ids (just uid) at a given location
    def get_agents_at_location(self, loc):
        agents_at_loc = []
        for id in list(self._agent_locations_and_energy.keys()):
            if self._agent_locations_and_energy[id][0] == loc:
                agents_at_loc.append(id)
        return agents_at_loc

    # Method that returns the list of ids of agents that are available and closest to rubble for helping
    # Parameters: World object, location of rubble, rubble removal energy, number of agents needed
    def get_closest_available_agent_for_rubble(self, world, loc, removal_energy, num):
        list_of_agents = list(self._agent_locations_and_energy.keys())
        list_of_selected_agents = []
        for _ in range(num):
            # Select the agent based on path distance
            min_dist = float('inf')
            selected_agent = None
            for id in list_of_agents:
                # Select only if agent is not helping someone else AND agent is not current agent
                if (not self._agent_location_of_helping[id] or self._agent_location_of_helping[id] == loc) and id != self._agent.get_agent_id().id:
                    # If path exists...
                    path_tuple = self.get_path_to_location(world, self._agent_locations_and_energy[id][0], loc)
                    if path_tuple:
                        path, path_cost = path_tuple
                        path_cost = path_cost + removal_energy  # Rubble removal energy is added to cost
                        if path_cost < self._agent_locations_and_energy[id][1]:
                            dist = len(path)
                            if dist < min_dist:
                                min_dist = dist
                                selected_agent = id

            # Remove selected agent from list_of_agents, and add it to list_of_selected_agents
            if selected_agent:
                list_of_agents.remove(selected_agent)
                list_of_selected_agents.append(selected_agent)

        return list_of_selected_agents

    # Method that cancels tasks of an agent, if any
    def cancel_tasks(self, id):
        for survivor in list(self._status_of_survivor.keys()):
            if self._status_of_survivor[survivor][1] == id:
                self._status_of_survivor[survivor] = (False, 0)
        return

    # Method that gives a task free agent the closest agent (who is saving a survivor) it can follow, incase help is needed
    # Returns id of the agent selected, None if no agent is selected
    def get_agent_to_follow(self, world):
        # Get a list of all agent ids
        all_agents = list(self._agent_locations_and_energy.keys())
        # Get a list of ids of agents which are saving a survivor
        agents_to_follow = []
        for loc in list(self._status_of_survivor.keys()):
            if self._status_of_survivor[loc][0] and self._status_of_survivor[loc][1] != 0:
                agents_to_follow.append(self._status_of_survivor[loc][1])

        # Select the closest agent from the list which is not being followed
        min_dist = float('inf')
        selected_agent = None
        for target in agents_to_follow:
            can_follow = True
            # check if any other agent is already following our target. If yes, then we can't follow our target
            for follower in all_agents:
                # Can only follow if the target agent is not being followed by another agent
                if follower != self._agent.get_agent_id().id and self._following_agent[follower] == target:
                    can_follow = False

            if can_follow:
                # Check if the current target is our closest target so far
                path_tuple = self.get_path_to_location(world, self._agent.get_location(), self._agent_locations_and_energy[target][0])
                if path_tuple:
                    dist = len(path_tuple[0])
                    if dist < min_dist:
                        min_dist = dist
                        selected_agent = target

        return selected_agent