import numpy as np
from objects.utils import local_space_to_world_space

class Collider:
    
    obj: 'objects.base.PhysicsObject' # noqa: F821

    def __init__(self, obj):
        self.physicsObject = obj

    def generateExtraPhysicsAttributes(self):
        raise NotImplementedError("Collider does not implement generateExtraPhysicsAttributes")

    def getCollisionInfo(self, other: 'Collider'):
        raise NotImplementedError("Collider does not implement getCollisionInfo")

    def initFromKwargs(self, **kwargs):
        pass

class Circle(Collider):

    radius: float

    def generateExtraPhysicsAttributes(self):
        self.physicsObject.inertia = 0.5 * self.physicsObject.mass * self.radius * self.radius

    def getCollisionInfo(self, other: Collider):
        if isinstance(other, Circle):
            displacement_vector = other.physicsObject.position - self.physicsObject.position
            distance = np.sqrt(pow(displacement_vector[0], 2) + pow(displacement_vector[1], 2))
            if distance < self.radius + other.radius:
                return {
                    'collision': True,
                    'world_space_position': displacement_vector * (self.radius / distance - 0.5*(1 - distance / (self.radius + other.radius))) + self.physicsObject.position,
                    'collision_vector': (-(self.radius + other.radius - distance) / distance) * displacement_vector
                }
            return {
                'collision': False
            }
        if isinstance(other, ConvexPolygon):
            # Find the closest intersection with the circle for each edge on the rectangle
            best_distance = self.radius + 100
            best_point = None
            for a, b in zip(other.verts[:-1], other.verts[1:]):
                # Vector from a to b, now in worldspace
                ws_b = local_space_to_world_space(b, other.physicsObject.rotation, other.physicsObject.position)
                ws_a = local_space_to_world_space(a, other.physicsObject.rotation, other.physicsObject.position)
                ws_vec = ws_b - ws_a
                a_to_circle = self.physicsObject.position[:2] - ws_a
                edge_length = np.sqrt(pow(ws_vec[0], 2) + pow(ws_vec[1], 2))
                edge_normalize = ws_vec / edge_length
                dotP = np.dot(a_to_circle, edge_normalize)
                if dotP < 0:
                    # Closest point is vertex a.
                    intersection_point = ws_a
                elif dotP > edge_length:
                    # Closest point is vertex b.
                    intersection_point = ws_b
                else:
                    # Closest point is ws_a + dotP * edge_normalize
                    intersection_point = ws_a + edge_normalize * dotP
                vec = intersection_point - self.physicsObject.position[:2]
                d = np.sqrt(pow(vec[0], 2) + pow(vec[1], 2))
                if d < best_distance:
                    best_distance = d
                    best_point = intersection_point
                    best_point = np.append(best_point, np.array([self.physicsObject.position[2]]))
            if best_distance < self.radius:
                return {
                    'collision': True,
                    'world_space_position': best_point,
                    'collision_vector': (self.physicsObject.position - best_point) * ((self.radius - best_distance) / best_distance)
                }
            return {
                'collision': False
            }
        raise ValueError(f"Collision not handled: Circle to {str(other)}")

    def initFromKwargs(self, **kwargs):
        super().initFromKwargs(**kwargs)
        self.radius = kwargs.get('radius', 100)

class ConvexPolygon(Collider):

    # These verts are defined relative to the centroid at 0,0.
    # Vertices should move counter-clockwise around the centroid, and include the first vertex at the start and end.
    verts: np.array

    def generateExtraPhysicsAttributes(self):
        # Generate inertia for each tri
        i = 0
        for a, b in zip(self.verts[:-1], self.verts[1:]):
            i += (pow(a[0], 2) + pow(a[1], 2) + pow(b[0], 2) + pow(b[1], 2) + np.dot(a, b)) / 6
        self.physicsObject.inertia = i * self.physicsObject.mass

    def getCollisionInfo(self, other: Collider):
        if isinstance(other, Circle):
            return other.getCollisionInfo(self)
        if isinstance(other, ConvexPolygon):
            # Use the separating axis method to generate collision info between two convex polygons.
            # STEP 1: Translate normals for each shape into worldspace.
            normals = []
            for i, n in enumerate(self.normals):
                normals.append((local_space_to_world_space(n, self.physicsObject.rotation, np.array([0, 0, 0])), 's', i))
            for i, n in enumerate(other.normals):
                normals.append((local_space_to_world_space(n, other.physicsObject.rotation, np.array([0, 0, 0])), 'e', i))
            # STEP 2: For each normal, calculate the overlap.
            self_points = [
                local_space_to_world_space(v, self.physicsObject.rotation, self.physicsObject.position)
                for v in self.verts
            ]
            other_points = [
                local_space_to_world_space(v, other.physicsObject.rotation, other.physicsObject.position)
                for v in other.verts
            ]
            best_collision = -1
            best_collision_point = None
            best_collision_vector = None
            for n, source, i in normals:
                # We need the source here, because any intersecting vertex will not be from the source.
                s_min = (1000000, None)
                s_max = (-1000000, None)
                o_min = (1000000, None)
                o_max = (-1000000, None)
                epsilon = 0.000001
                for p in range(len(self_points)):
                    res = np.dot(self_points[p], n)
                    if res - epsilon > s_max[0]:
                        s_max = (res, [p])
                    elif res + epsilon > s_max[0]:
                        s_max = (res, [p] + s_max[1])
                    if res + epsilon < s_min[0]:
                        s_min = (res, [p])
                    elif res - epsilon < s_min[0]:
                        s_min = (res, [p] + s_min[1])
                for p in range(len(other_points)):
                    res = np.dot(other_points[p], n)
                    if res - epsilon > o_max[0]:
                        o_max = (res, [p])
                    elif res + epsilon > o_max[0]:
                        o_max = (res, [p] + o_max[1])
                    if res + epsilon < o_min[0]:
                        o_min = (res, [p])
                    elif res - epsilon < o_min[0]:
                        o_min = (res, [p] + o_min[1])
                # Check intersection
                if s_min[0] > o_max[0] or s_max[0] < o_min[0]:
                    return {
                        'collision': False
                    }
                # STEP 3: If the maximal collision did occur on this normal, it is between two maximums.
                if source == 's':
                    # Check collision from other vertices
                    if s_min[0] < o_min[0] < s_max[0]:
                        if i in s_max[1]:
                            for p in o_min[1]:
                                edge = self_points[i] - self_points[i+1]
                                e1, e2 = np.dot(edge, self_points[i]), np.dot(edge, self_points[i+1])
                                if min(e1, e2) <= np.dot(edge, other_points[p]) <= max(e1, e2):
                                    if s_max[0] - o_min[0] > best_collision:
                                        best_collision = s_max[0] - o_min[0]
                                        best_collision_point = other_points[p]
                                        best_collision_vector = np.dot(n, best_collision_point - self_points[i+1]) * n / (pow(n[0], 2) + pow(n[1], 2))
                    if s_max[0] > o_max[0] > s_min[0]:
                        if i in s_min[1]:
                            for p in o_max[1]:
                                edge = self_points[i] - self_points[i+1]
                                e1, e2 = np.dot(edge, self_points[i]), np.dot(edge, self_points[i+1])
                                if min(e1, e2) <= np.dot(edge, other_points[p]) <= max(e1, e2):
                                    if o_max[0] - s_min[0] > best_collision:
                                        best_collision = o_max[0] - s_min[0]
                                        best_collision_point = other_points[p]
                                        best_collision_vector = np.dot(n, best_collision_point - self_points[i+1]) * n / (pow(n[0], 2) + pow(n[1], 2))
                else:
                    # Check collision from self vertices
                    if o_min[0] < s_min[0] < o_max[0]:
                        if i in o_max[1]:
                            for p in s_min[1]:
                                edge = other_points[i] - other_points[i+1]
                                e1, e2 = np.dot(edge, other_points[i]), np.dot(edge, other_points[i+1])
                                if min(e1, e2) <= np.dot(edge, self_points[p]) <= max(e1, e2):
                                    if o_max[0] - s_min[0] > best_collision:
                                        best_collision = o_max[0] - s_min[0]
                                        best_collision_point = self_points[p]
                                        best_collision_vector = -np.dot(n, best_collision_point - other_points[i+1]) * n / (pow(n[0], 2) + pow(n[1], 2))
                    if o_max[0] > s_max[0] > o_min[0]:
                        if i in o_min[1]:
                            for p in s_max[1]:
                                edge = other_points[i] - other_points[i+1]
                                e1, e2 = np.dot(edge, other_points[i]), np.dot(edge, other_points[i+1])
                                if min(e1, e2) <= np.dot(edge, self_points[p]) <= max(e1, e2):
                                    if s_max[0] - o_min[0] > best_collision:
                                        best_collision = s_max[0] - o_min[0]
                                        best_collision_point = self_points[p]
                                        best_collision_vector = -np.dot(n, best_collision_point - other_points[i+1]) * n / (pow(n[0], 2) + pow(n[1], 2))
            # If no collision point is found, then the interesection of the two shapes does not include a vertex, in a physics simulation, this barely happens. So simply let it occur.
            if best_collision_point is None:
                return {
                    'collision': False
                }
            best_collision_vector = np.append(best_collision_vector, [self.physicsObject.position[2]])
            return {
                'collision': True,
                'world_space_position': best_collision_point,
                'collision_vector': best_collision_vector
            } 
        raise ValueError(f"Collision not handled: ConvexPolygon to {str(other)}")
    
    def initFromKwargs(self, **kwargs):
        super().initFromKwargs(**kwargs)
        self.verts = np.array(kwargs.get('verts', [(0, 1), (-1, 0), (0, -1), (1, 0), (0, 1)]))
        # Also generate the normals across the edges.
        self.normals = np.array([
            ((b-a)[1], -(b-a)[0])
            for a, b in zip(self.verts[:-1], self.verts[1:])
        ])

def colliderFactory(physObj, **options):
    if 'name' not in options:
        raise ValueError("Tried to generate collider, but no 'name' field was supplied.")
    for klass in (Circle, ConvexPolygon):
        if options['name'] == klass.__name__:
            r = klass(physObj)
            r.initFromKwargs(**options)
            return r
    name = options['name']
    raise ValueError(f"Unknown collider, {name}")
