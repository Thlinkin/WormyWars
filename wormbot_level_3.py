# wormbot_level_3.py
from worm_class import *
from settings import *
from utilities import *
from game_clock import *
import random


class WormBotLevel3(Worm):
    """
    Hunting bot (preservation-first):
    - Grows until it has advantage, then hunts and attempts corrals/boxes.
    - Does NOT willingly trade deaths. Strongly avoids head-on.
    - Consults portal actions (if portal_points passed in).
    - Briefly "hunts" invisible worms using last-known position only if close.
    """

    is_robot = True

    # ---------------- Tuning knobs ----------------
    RAND_PART = 4.5

    GROW_MARGIN = 3
    CUT_MARGIN = 2
    BOX_MARGIN = 10
    VERY_LONG_LEN = 28

    IMPOSSIBLE = -1000.0
    HIT_PENALTY = 130.0
    WALL_PENALTY = 130.0
    EDGE_PENALTY = 150.0
    HEADON_PENALTY = 85.0

    # Portals (now evaluated using portal actions)
    PORTAL_RISK_PENALTY = 22.0        # base "portals are chaotic"
    PORTAL_BAD_ACTION_PENALTY = 200.0 # action None -> death in your main loop (avoid)
    PORTAL_UNSAFE_LAND_PENALTY = 80.0 # landing tile blocked -> likely death

    DEADEND_PENALTY = 45.0
    TUNNEL_PENALTY = 25.0

    # Fruit priorities (applied as opportunistic target selection)
    BLUEBERRY_BONUS = 40.0
    GOLDEN_BONUS = 18.0
    GRAPE_BONUS = 12.0
    BANANA_BONUS = 4.0
    LIME_BASE = 1.0                  # lime is risky: mostly avoid unless winning / safe

    TARGET_REEVAL_TIME = 1.2
    MODE_HOLD_TIME = 0.9
    STUCK_TIME = 9.0

    # Invisible hunt memory: short and only if close
    INVIS_HUNT_SECS = 1.1
    INVIS_HUNT_DIST = 7

    BOX_RADIUS_MIN = 3
    BOX_RADIUS_MAX = 5

    def __init__(self, worm_color, player_number):
        super().__init__(worm_color, player_number)
        self._init_hunter_state()

    def _init_hunter_state(self):
        self.hunt_target = None
        self.last_target_pick = -1000.0

        self.mode = "GROW"            # GROW / CUT_OFF / BOX / AREA_DENY / REPOSITION
        self.mode_until = -1000.0

        # last-known memory for invisible worms
        # {player_number: {'head':{x,y}, 'dir':dir, 'time':t, 'len':n}}
        self.last_seen = {}

        #GPT: Opening behavior: do not hunt until we've eaten some apples this level
        self.opening_apples_needed = 2  # prefer two apples before hunting
        self.opening_apples_eaten = 0
        self.opening_active = True
        self._last_score_seen = 0

    # ---------------- Low-level helpers ----------------

    def _is_edge(self, c):
        return (c['x'] < 0 or c['x'] >= CELLWIDTH or c['y'] < 0 or c['y'] >= CELLHEIGHT)

    def _same(self, a, b):
        return same_coord(a, b)

    def _coord_in(self, c, coords_list):
        for cc in coords_list:
            if self._same(c, cc):
                return True
        return False

    def _is_blocked(self, c, occupied, wall_coords):
        if self._is_edge(c):
            return True
        if self._coord_in(c, wall_coords):
            return True
        if self._coord_in(c, occupied):
            return True
        return False

    def _count_open_neighbors(self, c, occupied, wall_coords):
        open_count = 0
        for d in DIRECTIONS:
            n = get_new_head(d, [c])
            if self._is_edge(n):
                continue
            if self._coord_in(n, wall_coords):
                continue
            if self._coord_in(n, occupied):
                continue
            open_count += 1
        return open_count


    #GPT early apple system
    def _update_opening_state(self):
        """
        Force early growth: at the start of each level (or after respawn),
        the bot will go for apples until it has gained some points from apples.

        We infer "apples eaten" via score increases. Apples add apple_number (1,2,3,...),
        so the first two apples always increase score by at least 1 and then 2.
        """
        # Detect reset/new level/respawn: worm usually starts at length 3
        if len(self.coords) <= 3:
            # Re-arm opening phase when we're tiny again
            self.opening_active = True
            self.opening_apples_eaten = 0
            self._last_score_seen = self.score
            return

        # Track score gain since last frame
        if self.score > self._last_score_seen:
            delta = self.score - self._last_score_seen
            self._last_score_seen = self.score

            # Heuristic: if we're in opening, count any positive gain as "an apple"
            # (If you want to be stricter, we can try to exclude fruit point values.)
            if self.opening_active:
                self.opening_apples_eaten += 1
                if self.opening_apples_eaten >= self.opening_apples_needed:
                    self.opening_active = False


    # ---------------- Portal action consulting ----------------

    def _build_portal_map(self, portal_points):
        # key by (x,y) tuple
        pmap = {}
        if portal_points is None:
            return pmap
        for p in portal_points:
            try:
                pmap[(p.coord['x'], p.coord['y'])] = p
            except Exception:
                continue
        return pmap

    def _simulate_portal(self, portal_map, portal_coord, direction):
        """
        Returns: (is_bad, new_coord, new_direction)
        - is_bad True means action is None (death)
        - if portal not found in map, treat as unknown portal: (False, None, None)
        """
        key = (portal_coord['x'], portal_coord['y'])
        if key not in portal_map:
            return False, None, None

        portal_point = portal_map[key]
        action = portal_point.get_action(direction)
        if action is None:
            return True, None, None
        return False, action.new_coord, action.new_direction

    # ---------------- Fruit handling ----------------

    def _get_existing_fruits_with_types(self, fruits):
        # fruits from main: [banana, grape, lime, blueberry, golden_apple]
        banana, grape, lime, blueberry, golden = fruits
        out = []
        if len(blueberry) > 0:
            out.append((blueberry, 'blueberry'))
        if len(golden) > 0:
            out.append((golden, 'golden'))
        if len(grape) > 0:
            out.append((grape, 'grape'))
        if len(banana) > 0:
            out.append((banana, 'banana'))
        if len(lime) > 0:
            out.append((lime, 'lime'))
        return out

    def _fruit_value(self, kind):
        if kind == 'blueberry':
            return self.BLUEBERRY_BONUS
        if kind == 'golden':
            return self.GOLDEN_BONUS
        if kind == 'grape':
            return self.GRAPE_BONUS
        if kind == 'banana':
            return self.BANANA_BONUS
        if kind == 'lime':
            return self.LIME_BASE
        return 0.0

    # ---------------- Visibility memory ----------------

    def _update_last_seen(self, visible_worms_info):
        now = current_time()
        # update entries for currently visible worms
        for w in visible_worms_info:
            if w.player_number == self.player_number:
                continue
            if w.coords is None or len(w.coords) == 0:
                continue
            self.last_seen[w.player_number] = {
                'head': w.coords[HEAD],
                'dir': w.direction,
                'time': now,
                'len': len(w.coords)
            }

        # prune stale memory
        to_del = []
        for pn, mem in self.last_seen.items():
            if (now - mem['time']) > (self.INVIS_HUNT_SECS * 2.2):
                to_del.append(pn)
        for pn in to_del:
            del self.last_seen[pn]

    def _get_ghost_target_info(self, player_number):
        if player_number not in self.last_seen:
            return None
        mem = self.last_seen[player_number]
        age = current_time() - mem['time']
        if age > self.INVIS_HUNT_SECS:
            return None
        # only hunt briefly if close
        dist = total_distance_to_target(self.coords[HEAD], mem['head'])
        if dist > self.INVIS_HUNT_DIST:
            return None
        return mem

    # ---------------- Target selection + mode ----------------

    def _pick_target(self, visible_worms_info):
        now = current_time()
        if (now - self.last_target_pick) < self.TARGET_REEVAL_TIME and self.hunt_target is not None:
            return self.hunt_target

        my_head = self.coords[HEAD] if len(self.coords) > 0 else None
        if my_head is None:
            self.hunt_target = None
            self.last_target_pick = now
            return None

        my_len = len(self.coords)

        best = None
        best_score = -1e9

        # First, score visible targets
        for w in visible_worms_info:
            if w.player_number == self.player_number:
                continue
            if w.coords is None or len(w.coords) == 0:
                continue

            t_head = w.coords[HEAD]
            t_len = len(w.coords)
            dist = total_distance_to_target(my_head, t_head)

            edge_vuln = 0.0
            if t_head['x'] <= 3 or t_head['x'] >= CELLWIDTH - 4:
                edge_vuln += 6.0
            if t_head['y'] <= 3 or t_head['y'] >= CELLHEIGHT - 4:
                edge_vuln += 6.0

            delta = my_len - t_len

            # human preference proxy (works even without is_robot info)
            humanish = 0.0
            if w.player_number <= 1:
                humanish += 2.0
            elif w.player_number <= 2:
                humanish += 1.0

            short_bonus = max(0.0, 8.0 - 0.6 * t_len)
            close_bonus = max(0.0, 20.0 - dist)
            adv_bonus = 2.5 * delta

            score = close_bonus + edge_vuln + short_bonus + humanish + adv_bonus
            if score > best_score:
                best_score = score
                best = w.player_number

        # If none visible, optionally hunt a ghost target (briefly + close)
        if best is None:
            # choose best ghost among stored last_seen that is still fresh and close
            for pn, mem in self.last_seen.items():
                ghost = self._get_ghost_target_info(pn)
                if ghost is None:
                    continue
                dist = total_distance_to_target(my_head, ghost['head'])
                # small preference for lower player num still
                score = (15.0 - dist) + (2.0 if pn <= 1 else 0.0)
                if score > best_score:
                    best_score = score
                    best = pn

        self.hunt_target = best
        self.last_target_pick = now
        return best

    def _get_visible_target(self, visible_worms_info, target_num):
        if target_num is None:
            return None
        for w in visible_worms_info:
            if w.player_number == target_num:
                return w
        return None

    def _decide_mode(self, target_len, portal_coords):
        now = current_time()
        if now < self.mode_until:
            return self.mode

        my_len = len(self.coords)
        stuck = elapsed_time(self.last_point_time) > self.STUCK_TIME

        mode = "GROW"
        if target_len is None:
            mode = "REPOSITION"
        else:
            delta = my_len - target_len

            if my_len >= self.VERY_LONG_LEN:
                mode = "AREA_DENY"

            if stuck and len(portal_coords) > 0:
                mode = "REPOSITION"

            if delta >= self.BOX_MARGIN:
                mode = "BOX"
            elif delta >= self.CUT_MARGIN:
                mode = "CUT_OFF"
            elif delta < self.GROW_MARGIN:
                mode = "GROW"

        self.mode = mode
        self.mode_until = now + self.MODE_HOLD_TIME
        return mode

    def _choose_objective(self, mode, target_visible, target_head, target_dir,
                          target_len, portal_coords, wall_coords, apple, fruits):
        my_head = self.coords[HEAD]
        my_len = len(self.coords)

        # Opportunistic fruit choice
        fruits_with_types = self._get_existing_fruits_with_types(fruits)
        best_fruit = None
        best_score = -1e9
        for (fc, kind) in fruits_with_types:
            dist = total_distance_to_target(my_head, fc)
            val = self._fruit_value(kind)
            score = val - 0.9 * dist

            # lime is risky: suppress unless we are already advantaged or long
            if kind == 'lime' and my_len < 14:
                score -= 25.0

            # avoid baiting into obvious dead-ends
            if self._count_open_neighbors(fc, [], wall_coords) <= 0:
                score -= 100.0

            if score > best_score:
                best_score = score
                best_fruit = (fc, kind)

        # defaults
        objective = apple
        scale = 1.15

        if mode == "GROW":
            # go apple unless a strong fruit is attractive (blueberry)
            if best_fruit is not None and best_fruit[1] == 'blueberry' and best_score > 15.0:
                objective = best_fruit[0]
                scale = 1.15
            else:
                objective = apple
                scale = 1.25

        elif mode == "CUT_OFF":
            # intercept 2 steps ahead if we can see them; if ghost, intercept 1 step
            if target_head is not None and target_dir is not None:
                t1 = get_new_head(target_dir, [target_head])
                t2 = get_new_head(target_dir, [t1])
                objective = t2 if target_visible else t1
                scale = 1.45

            # blueberry opportunism even while hunting
            if best_fruit is not None and best_fruit[1] == 'blueberry' and best_score > 22.0:
                objective = best_fruit[0]
                scale = 1.35

        elif mode == "BOX":
            if target_head is not None and target_len is not None:
                delta = my_len - target_len
                R = self.BOX_RADIUS_MIN + min(self.BOX_RADIUS_MAX - self.BOX_RADIUS_MIN, int(delta / 6))
                candidates = [
                    {'x': target_head['x'] + R, 'y': target_head['y']},
                    {'x': target_head['x'] - R, 'y': target_head['y']},
                    {'x': target_head['x'], 'y': target_head['y'] + R},
                    {'x': target_head['x'], 'y': target_head['y'] - R},
                ]
                best = None
                bestd = 1e9
                for c in candidates:
                    if self._is_edge(c):
                        continue
                    d = total_distance_to_target(my_head, c)
                    if d < bestd:
                        bestd = d
                        best = c
                if best is not None:
                    objective = best
                    scale = 1.25

        elif mode == "AREA_DENY":
            center = {'x': CELLWIDTH // 2, 'y': CELLHEIGHT // 2}
            objective = center
            scale = 1.0

            # prioritize blueberry, then golden
            if best_fruit is not None and best_fruit[1] == 'blueberry' and best_score > 10.0:
                objective = best_fruit[0]
                scale = 1.05
            elif best_fruit is not None and best_fruit[1] == 'golden' and best_score > 12.0:
                objective = best_fruit[0]
                scale = 1.02

        elif mode == "REPOSITION":
            if len(portal_coords) > 0:
                p, _ = closest_portal(my_head, portal_coords)
                objective = p
                scale = 1.15
            else:
                objective = {'x': CELLWIDTH // 2, 'y': CELLHEIGHT // 2}
                scale = 1.0

        return objective, scale

    # ---------------- Main decision ----------------

    def choose_direction(self, visible_worms_info, portal_coords, wall_coords, apple, fruits, portal_points=None):
        # update last-seen memory for invisible hunting
        self._update_opening_state() #GPT line
        self._update_last_seen(visible_worms_info)

        # build portal lookup (coord -> PortalPoint)
        portal_map = self._build_portal_map(portal_points)

        # Base goodness with randomness
        goodness = [
            random.random() * self.RAND_PART,
            random.random() * self.RAND_PART,
            random.random() * self.RAND_PART,
            random.random() * self.RAND_PART
        ]

        # prefer going straight
        goodness[DIRECTIONS.index(self._direction)] += 4.0

        # never reverse
        goodness[D_OPPOSITE.index(self._direction)] = self.IMPOSSIBLE

        # pick target
        target_num = self._pick_target(visible_worms_info)
        target_info = self._get_visible_target(visible_worms_info, target_num)

        target_visible = False
        target_head = None
        target_dir = None
        target_len = None

        if target_info is not None and target_info.coords is not None and len(target_info.coords) > 0:
            target_visible = True
            target_head = target_info.coords[HEAD]
            target_dir = target_info.direction
            target_len = len(target_info.coords)
        else:
            ghost = self._get_ghost_target_info(target_num) if target_num is not None else None
            if ghost is not None:
                target_visible = False
                target_head = ghost['head']
                target_dir = ghost['dir']
                target_len = ghost['len']

        # decide mode GPT
        mode = self._decide_mode(target_len, portal_coords)

        # Opening: always grow on apples for the first couple points
        if self.opening_active:
            mode = "GROW"
            # Make apples the goal no matter what
            objective = apple
            obj_scale = 1.35
        else:
            objective, obj_scale = self._choose_objective(
                mode, target_visible, target_head, target_dir, target_len,
                portal_coords, wall_coords, apple, fruits
            )

        # move toward objective
        goodness = prefer_direction_to_target(self.coords, objective, goodness, scale=obj_scale)

        # occupied tiles (visible worms + our body)
        visible_worm_coords = collect_worms_coords(visible_worms_info)
        occupied = visible_worm_coords + self.coords

        # predicted next heads of visible worms (for head-on avoidance)
        predicted_next_heads = []
        for w in visible_worms_info:
            if w.player_number == self.player_number:
                continue
            if w.coords is None or len(w.coords) == 0:
                continue
            predicted_next_heads.append(get_new_head(w.direction, w.coords))

        # evaluate each direction
        for jj in range(4):
            d = DIRECTIONS[jj]
            new_head = get_new_head(d, self.coords)

            # edges/walls/body
            if self._is_edge(new_head):
                goodness[jj] -= self.EDGE_PENALTY
                continue

            if self._coord_in(new_head, wall_coords):
                goodness[jj] -= self.WALL_PENALTY
                continue

            if self._coord_in(new_head, occupied):
                goodness[jj] -= self.HIT_PENALTY
                continue

            # head-on risk: stepping into predicted next head tiles
            for nh in predicted_next_heads:
                if same_coord(new_head, nh):
                    goodness[jj] -= self.HEADON_PENALTY

            # tunnel / dead-end aversion
            open_n = self._count_open_neighbors(new_head, occupied, wall_coords)
            if open_n <= 1:
                goodness[jj] -= self.DEADEND_PENALTY
            elif open_n == 2:
                side1 = get_new_head(D_ALTERNATE[jj], [new_head])
                side2 = get_new_head(D_ALT_ALT[jj], [new_head])
                if self._is_blocked(side1, occupied, wall_coords) and self._is_blocked(side2, occupied, wall_coords):
                    goodness[jj] -= self.TUNNEL_PENALTY

            # portal evaluation using actions (if it is a portal tile)
            if self._coord_in(new_head, portal_coords):
                # base risk
                goodness[jj] -= self.PORTAL_RISK_PENALTY

                bad, land, ndir = self._simulate_portal(portal_map, new_head, d)

                # If we know stepping on it kills us, strongly avoid.
                if bad:
                    goodness[jj] -= self.PORTAL_BAD_ACTION_PENALTY
                elif land is not None:
                    # If landing is blocked, avoid.
                    if self._is_edge(land) or self._coord_in(land, wall_coords) or self._coord_in(land, occupied):
                        goodness[jj] -= self.PORTAL_UNSAFE_LAND_PENALTY
                    else:
                        # If portal safely relocates us, it's not terrible (small reward)
                        goodness[jj] += 4.0

            # modest cutoff reward: if hunting and we move near target
            if mode in ("CUT_OFF", "BOX") and target_head is not None:
                dist_now = total_distance_to_target(self.coords[HEAD], target_head)
                dist_new = total_distance_to_target(new_head, target_head)
                if dist_new < dist_now:
                    goodness[jj] += 3.0

            # boxing tightening reward (only when target is visible; grape should help escape)
            if mode == "BOX" and target_visible and target_head is not None and target_len is not None:
                dist_to_target = total_distance_to_target(new_head, target_head)
                if self.BOX_RADIUS_MIN <= dist_to_target <= self.BOX_RADIUS_MAX:
                    goodness[jj] += 8.0
                if dist_to_target <= 1:
                    goodness[jj] -= 14.0  # too close is risky
                if dist_to_target == 1:
                    goodness[jj] += 6.0   # blocks an exit

            # if target is invisible (ghost hunting), reduce commitment a bit (helps grape escape)
            if (not target_visible) and target_head is not None:
                # don't over-commit: add mild randomness and reduce aggressive moves
                goodness[jj] -= 2.0

        # pick best
        best_index = goodness.index(max(goodness))
        self._direction = DIRECTIONS[best_index]
