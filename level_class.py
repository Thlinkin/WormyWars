from settings import *


class Action:

    def __init__(self, new_coord, new_direction):
        self.new_coord = new_coord
        self.new_direction = new_direction


class PortalPoint:

    def __init__(self, coord, left_action=None, right_action=None,
                 up_action=None, down_action=None):

        self.coord = coord
        self.left_action = left_action
        self.right_action = right_action
        self.up_action = up_action
        self.down_action = down_action

    def get_action(self, direction):

        if direction == LEFT:
            return self.left_action
        elif direction == RIGHT:
            return self.right_action
        elif direction == UP:
            return self.up_action
        elif direction == DOWN:
            return self.down_action


# class Portal:
#     def __init__(self, portal_points):
#         self.portal_points = portal_points

# Examples of making instances of classes
# coord = {'x': 56, 'y': 65}
#
# paction = Action(coord, LEFT)
#
# p1 = PortalPoint(coord,
#                  left_action=Action(coord, LEFT),
#                  right_action=Action({'x': 678, 'y':34}, DOWN))

def expand_walls(wall_defs):
    expanded = []
    for w in wall_defs:
        xs = w['x']
        ys = w['y']

        # If x is a range, expand it; otherwise make it a list of one
        if isinstance(xs, range):
            xs = list(xs)
        else:
            xs = [xs]

        # Same for y
        if isinstance(ys, range):
            ys = list(ys)
        else:
            ys = [ys]

        # Produce all combinations of x and y
        for x in xs:
            for y in ys:
                expanded.append({'x': x, 'y': y})

    return expanded

class Level:
    def __init__(self, number, name, portals, walls, num_apples):

        self.portals = portals
        self.walls = expand_walls(walls)
        self.number = number
        self.name = name
        self.num_apples = num_apples

    def get_all_portal_coords(self):
        all_portals_coords = []

        for portal_point in self.portals:
            all_portals_coords.append(portal_point.coord)

        return all_portals_coords
