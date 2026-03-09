from settings import *
import pygame
import utilities as utils
from game_clock import *

HEAD = 0  # syntactic sugar: index of the worm's head


def collect_worms_coords(worms):
    coord_list = []
    for worm in worms:
        coord_list = coord_list + worm.coords

    return coord_list


def all_visible_worm_coords(worms):
    coord_list = []
    for worm in worms:
        if worm.is_in_play and worm.is_visible():
            coord_list = coord_list + worm.coords

    return coord_list


def all_visible_worm_nums(worms):
    nums = []
    for ii in range(len(worms)):
        if worms[ii].is_in_play and worms[ii].is_visible():
            nums.append(ii)

    return nums


def gather_visible_worms_info(worms):
    nums = all_visible_worm_nums(worms)
    worms_info = []
    for ii in nums:
        worms_info.append(worms[ii].get_worm_info())

    return worms_info


def get_new_head(use_direction, use_coords):
    new_head = []
    if use_direction == UP:
        new_head = {'x': use_coords[HEAD]['x'], 'y': use_coords[HEAD]['y'] - 1}
    elif use_direction == DOWN:
        new_head = {'x': use_coords[HEAD]['x'], 'y': use_coords[HEAD]['y'] + 1}
    elif use_direction == LEFT:
        new_head = {'x': use_coords[HEAD]['x'] - 1, 'y': use_coords[HEAD]['y']}
    elif use_direction == RIGHT:
        new_head = {'x': use_coords[HEAD]['x'] + 1, 'y': use_coords[HEAD]['y']}

    return new_head  # return the head (don't add it) because it could be used for testing a path


class WormInfo:

    def __init__(self):
        self.player_number = []
        self.coords = []
        self.direction = []
        self.is_in_play = []
        #chatgpt below
        self.is_robot = False
        self.num_lives = 0
        self.score = 0
        self.last_portal_time = -1000.0
        self.last_point_time = -1000.0
        #gptend

class Worm:
    coords = []
    _direction = []
    num_lives = []
    score = []
    is_in_play = []
    num_to_grow = []
    num_turbos = []
    turbo_end_time = []
    freeze_end_time = []
    invisible_end_time = []
    fade_start_time = []
    is_shrinking = []

    started_dying_time = []
    last_shrink_time = []
    last_press_time = []
    last_portal_time = []
    last_grow_time = []
    last_point_time = []

    last_key_press = []

    is_dying = []
    is_robot = False
    starting_turbos = NUM_TURBOS

    def __init__(self, worm_color, player_number):
        self.is_in_play = True
        self.color = worm_color
        self.player_number = player_number
        self.num_lives = NUM_LIVES + 1
        self.score = 0
        self.birth([])  # Don't need coords here, wait for new_level call

    def get_worm_info(self):
        my_info = WormInfo()
        my_info.coords = self.coords
        my_info.direction = self._direction
        my_info.player_number = self.player_number
        #gpt
        my_info.is_in_play = self.is_in_play

        my_info.is_robot = self.is_robot
        my_info.num_lives = self.num_lives
        my_info.score = self.score
        my_info.last_portal_time = self.last_portal_time
        my_info.last_point_time = self.last_point_time

        return my_info

    def birth(self, starting_coords):
        if self.is_in_play:
            self.started_dying_time = None

            if self.num_lives > 0:
                self.num_lives -= 1
                if self.num_lives <= 0:
                    self.is_in_play = False
                    self.coords = []
                    return

            self.coords = starting_coords
            self.is_in_play = True
            self.is_dying = False
            self.num_turbos = self.starting_turbos

            self.reset()

        else:
            self.coords = []

    def new_level(self, starting_coords):
        self.reset()

        if self.is_dying:
            self.is_dying = False

            if self.num_lives > 0:
                self.num_lives -= 1
                if self.num_lives <= 0:
                    self.is_in_play = False
                    return

        if self.is_in_play:
            self.coords = starting_coords
        else:
            self.coords = []

    def reset(self):
        self.num_to_grow = 0

        self.is_shrinking = False
        self.turbo_end_time = 0
        self.freeze_end_time = 0
        self.invisible_end_time = 0
        self.fade_start_time = -100.0
        self.last_shrink_time = -100
        self.last_press_time = -100
        self.last_portal_time = -100
        self.last_grow_time = current_time()
        self.last_point_time = current_time()
        self.last_key_press = None

        if self.is_robot:
            self._direction = LEFT
        else:
            self._direction = RIGHT

    def die(self):
        self.reset()
        self.is_dying = True
        self.started_dying_time = current_time()

    def terminate(self):
        self.num_lives = 0
        self.is_in_play = False

    def is_dead(self):
        if self.started_dying_time is None:
            return False
        else:
            return elapsed_time(self.started_dying_time) > DYING_TIME_IN_SECS

    def is_fading_in(self):
        return self.invisible_end_time < current_time() < self.invisible_end_time + NUM_SECS_IN_FADE

    def is_fading_out(self):
        return (self.invisible_end_time - NUM_SECS_IN_INVISIBLE) < current_time() \
            < (self.invisible_end_time - NUM_SECS_IN_INVISIBLE + NUM_SECS_IN_FADE)

    def is_visible(self):
        return self.is_fading_out() or self.is_fading_in() or current_time() > self.invisible_end_time

    def is_in_turbo(self):
        return current_time() < self.turbo_end_time

    def is_frozen(self):
        return current_time() < self.freeze_end_time

    def freeze(self):
        if self.is_frozen():
            self.freeze_end_time += NUM_SECS_IN_FREEZE
        else:
            self.freeze_end_time = current_time() + NUM_SECS_IN_FREEZE

    def make_invisible(self):
        if self.is_visible():
            self.fade_start_time = current_time()
            self.invisible_end_time = current_time() + NUM_SECS_IN_INVISIBLE
        else:
            self.invisible_end_time += NUM_SECS_IN_INVISIBLE

    def go_turbo(self):
        if self.num_turbos > 0:
            if self.is_in_turbo():
                self.turbo_end_time += NUM_SECS_IN_TURBO
            else:
                self.turbo_end_time = current_time() + NUM_SECS_IN_TURBO

            self.num_turbos -= 1

    def add_turbo(self):
        self.num_turbos += 1

    def add_score(self, new_score):
        self.score += new_score
        self.last_point_time = current_time()

    def draw(self, display_surface):
        if self.is_in_play:
            inner_size = CELLSIZE - 8
            inner_offset = 4
            outer_size = CELLSIZE

            cc = 0
            for coord in self.coords:
                x = coord['x'] * CELLSIZE
                y = coord['y'] * CELLSIZE

                if self.is_frozen():
                    worm_frozen_rect = pygame.Rect(x, y, outer_size, outer_size)
                    pygame.draw.rect(display_surface, LIGHTBLUE, worm_frozen_rect)

                # Do outer worm blocks
                if cc % 2 == 0:
                    block_color = self.color
                else:
                    if self.is_robot:
                        block_color = PURPLE
                    else:
                        block_color = DARKGREEN

                if self.is_in_turbo():
                    block_color = utils.get_shifting_color([block_color, WHITE], 1.0)

                if self.is_frozen():
                    block_color = utils.get_shifting_color([block_color, LIGHTBLUE], 1.0)
                    use_outer_size = outer_size - 4
                    use_outer_offset = 2
                else:
                    use_outer_size = outer_size
                    use_outer_offset = 0

                if self.is_dying:
                    block_color = utils.get_pulse_color([block_color, BLACK], pulse_time=DYING_TIME_IN_SECS * 2.0,
                                                        pulse_start_time=self.started_dying_time)
                elif self.is_fading_out():
                    block_color = utils.get_pulse_color([block_color, BLACK], pulse_time=NUM_SECS_IN_FADE * 2.0,
                                                        pulse_start_time=self.fade_start_time)
                elif self.is_fading_in():
                    block_color = utils.get_pulse_color([BLACK, block_color], pulse_time=NUM_SECS_IN_FADE * 2.0,
                                                        pulse_start_time=self.fade_start_time + NUM_SECS_IN_INVISIBLE)
                elif not self.is_visible():
                    block_color = BLACK
                worm_outer_rect = pygame.Rect(x + use_outer_offset, y + use_outer_offset,
                                              use_outer_size, use_outer_size)
                pygame.draw.rect(display_surface, block_color, worm_outer_rect)

                # Do inner blocks
                if cc > 0:
                    if cc % 2 == 0:
                        if self.is_robot:
                            block_color = PURPLE
                        else:
                            block_color = DARKGREEN
                    else:
                        block_color = self.color

                    if self.is_shrinking:
                        block_color = utils.get_shifting_color([block_color, BLACK], 2.0)

                    if self.is_frozen():
                        block_color = utils.get_shifting_color([block_color, LIGHTBLUE], 1.0)

                    if self.is_dying:
                        block_color = utils.get_pulse_color([block_color, BLACK], pulse_time=DYING_TIME_IN_SECS * 1.0,
                                                            pulse_start_time=self.started_dying_time)
                    elif self.is_fading_out():
                        block_color = utils.get_pulse_color([block_color, BLACK], pulse_time=NUM_SECS_IN_FADE * 2.0,
                                                            pulse_start_time=self.fade_start_time)
                    elif self.is_fading_in():
                        block_color = utils.get_pulse_color([BLACK, block_color], pulse_time=NUM_SECS_IN_FADE * 2.0,
                                                            pulse_start_time=self.fade_start_time)
                    if not self.is_visible():
                        block_color = BLACK

                    worm_inner_rect = pygame.Rect(x + inner_offset, y + inner_offset, inner_size, inner_size)
                    pygame.draw.rect(display_surface, block_color, worm_inner_rect)

                cc += 1

    def set_direction(self, direction):
        self._direction = direction

    def get_direction(self):
        return self._direction

    def choose_direction(self, visible_worms_info, portal_coords, apple, fruits):
        if not self.is_robot:
            raise TypeError("Only a WormBot can choose its direction")

    def move(self):
        if self.is_frozen() or self.is_dying or self.is_dead():
            return

        # move the worm by adding a segment in the direction it is moving
        new_head = get_new_head(self._direction, self.coords)
        self.coords.insert(0, new_head)

        # delete the tail unless growing
        if self.num_to_grow > 0:
            # Don't delete the tail, grow instead!
            self.num_to_grow -= 1
        else:
            del self.coords[-1]  # remove worm's tail segment

        if self.is_shrinking and (current_time() - self.last_shrink_time > SHRINK_SEG_TIME):
            self.last_shrink_time = current_time()
            if len(self.coords) == 1:
                self.die()
            else:
                del self.coords[-1]  # remove worm's tail segment

    def grow(self, num_to_grow):
        self.is_shrinking = False
        self.num_to_grow += num_to_grow
        self.last_grow_time = current_time()

    def shrink(self):
        self.num_to_grow = 0
        self.is_shrinking = True

    def add_life(self):
        self.num_lives += 1

    def reverse(self):
        tail_direction = self.get_tail_direction()
        self._direction = D_OPPOSITE[DIRECTIONS.index(tail_direction)]
        self.coords.reverse()

    def get_tail_direction(self):
        last = len(self.coords) - 1
        last_m1 = last - 1

        if self.coords[last]['y'] == self.coords[last_m1]['y']:
            if self.coords[last]['x'] > self.coords[last_m1]['x']:
                direction = LEFT
            else:
                direction = RIGHT
        else:
            if self.coords[last]['y'] > self.coords[last_m1]['y']:
                direction = UP
            else:
                direction = DOWN

        return direction

    def switcheroo(self):
        pass  # TODO:!

    def hit_portal(self):
        self.last_portal_time = current_time()

#gpt below
def prefer_direction_to_target(worm_coords, target, goodness, scale=1.0):
    x_dist, y_dist = utils.xy_distance_to_target(worm_coords[HEAD], target)
    preferred_x_ix = None
    preferred_y_ix = None

    if x_dist > 0:
        goodness[IX_R] += 5.0 * scale
        preferred_x_ix = IX_R
    elif x_dist < 0:
        goodness[IX_L] += 5.0 * scale
        preferred_x_ix = IX_L

    if y_dist > 0:
        goodness[IX_D] += 5.0 * scale
        preferred_y_ix = IX_D
    elif y_dist < 0:
        goodness[IX_U] += 5.0 * scale
        preferred_y_ix = IX_U

    # If we're already on target, no preference needed
    if preferred_x_ix is None and preferred_y_ix is None:
        return goodness

    # Add some goodness to the direction most in the direction of the target.
    # Add a little goodness to an alternate direction in case the preferred is blocked.

    if abs(x_dist) > abs(y_dist):
        # prefer x if it exists; otherwise fall back to y
        primary = preferred_x_ix if preferred_x_ix is not None else preferred_y_ix
        goodness[primary] += 5.0 * scale
        goodness[DIRECTIONS.index(D_ALTERNATE[primary])] += 4.0 * scale
    else:
        # prefer y if it exists; otherwise fall back to x
        primary = preferred_y_ix if preferred_y_ix is not None else preferred_x_ix
        goodness[primary] += 5.0 * scale
        goodness[DIRECTIONS.index(D_ALTERNATE[primary])] += 4.0 * scale

    return goodness
