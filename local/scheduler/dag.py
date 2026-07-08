"""
Memento-X 依赖图构建 + 拓扑排序 + 循环检测

工作流步骤之间存在 depends_on 依赖关系，此模块负责：
1. 构建有向无环图（DAG）
2. 检测循环依赖（若有，报错）
3. 拓扑排序确定执行顺序
4. 分组：同一层级的无依赖步骤可并行执行

示例：
  step_1: scene_edit（无依赖）
  step_2: replace，depends_on: ["step_1"]
  step_3: replace，depends_on: ["step_1"]
  step_4: composite，depends_on: ["step_2", "step_3"]

  拓扑排序：[step_1] → [step_2, step_3] → [step_4]
  并行分组：[[step_1], [step_2, step_3], [step_4]]
"""
from collections import deque
from typing import List, Dict, Set, Tuple


class CycleDetectedError(Exception):
    """检测到循环依赖"""
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        cycle_str = " → ".join(cycle)
        super().__init__(f"检测到循环依赖: {cycle_str}")


class MissingDependencyError(Exception):
    """引用了不存在的步骤"""
    def __init__(self, step_id: str, missing_dep: str):
        super().__init__(f"步骤 '{step_id}' 依赖了不存在的步骤 '{missing_dep}'")


def build_dag(steps: List[dict]) -> Dict[str, Set[str]]:
    """
    从步骤列表构建依赖图（邻接表）。

    Args:
        steps: 工作流步骤列表，每个 step 含 id, depends_on 字段

    Returns:
        dict: {step_id: {依赖的 step_id 集合}}

    Raises:
        MissingDependencyError: 如果依赖的步骤不存在
    """
    all_ids = {s["id"] for s in steps}

    # 验证所有依赖引用存在
    for step in steps:
        for dep in step.get("depends_on", []):
            if dep not in all_ids:
                raise MissingDependencyError(step["id"], dep)

    # 构建邻接表：step_id → 它依赖的步骤集合
    dag: Dict[str, Set[str]] = {}
    for step in steps:
        sid = step["id"]
        dag[sid] = set(step.get("depends_on", []))

    return dag


def detect_cycle(dag: Dict[str, Set[str]]) -> List[str] | None:
    """
    DFS 检测循环依赖。

    Args:
        dag: 依赖图邻接表

    Returns:
        List[str] | None: 循环路径（如果存在），否则 None
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in dag}
    parent = {}

    def dfs(node: str) -> List[str] | None:
        color[node] = GRAY
        for dep in dag.get(node, set()):
            if color[dep] == GRAY:
                # 找到循环，回溯路径
                cycle = [dep, node]
                curr = node
                while curr in parent and parent[curr] != dep:
                    curr = parent[curr]
                    cycle.append(curr)
                cycle.append(dep)
                cycle.reverse()
                return cycle
            if color[dep] == WHITE:
                parent[dep] = node
                result = dfs(dep)
                if result:
                    return result
        color[node] = BLACK
        return None

    for node in dag:
        if color[node] == WHITE:
            cycle = dfs(node)
            if cycle:
                return cycle

    return None


def topological_sort(dag: Dict[str, Set[str]]) -> List[str]:
    """
    拓扑排序（Kahn 算法）。

    Args:
        dag: 依赖图邻接表 {step_id: {依赖的 step_id 集合}}

    Returns:
        List[str]: 拓扑排序后的步骤 ID 列表

    Raises:
        CycleDetectedError: 如果检测到循环依赖
    """
    # 检查循环
    cycle = detect_cycle(dag)
    if cycle:
        raise CycleDetectedError(cycle)

    # 构建反向图：step_id → 依赖它的步骤集合
    reverse: Dict[str, Set[str]] = {node: set() for node in dag}
    for node, deps in dag.items():
        for dep in deps:
            if dep in reverse:
                reverse[dep].add(node)

    # 计算入度（有多少步骤依赖它）
    in_degree = {node: len(dag.get(node, set())) for node in dag}

    # Kahn 算法
    queue = deque([node for node, deg in in_degree.items() if deg == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)

        for dependent in reverse.get(node, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # 如果结果数量不等于节点总数，说明有未处理的节点（循环）
    if len(result) != len(dag):
        remaining = set(dag.keys()) - set(result)
        raise CycleDetectedError(list(remaining))

    return result


def get_parallel_groups(dag: Dict[str, Set[str]]) -> List[List[str]]:
    """
    将拓扑排序后的步骤按层级分组，同层步骤可并行执行。

    算法：
    1. 计算每个节点的"深度"（最长依赖链长度）
    2. 同深度的节点归为一组

    Args:
        dag: 依赖图邻接表

    Returns:
        List[List[str]]: 按层级分组的步骤 ID 列表
    """
    # 计算深度（从叶子到根的最长路径）
    depth_cache: Dict[str, int] = {}

    def get_depth(node: str) -> int:
        if node in depth_cache:
            return depth_cache[node]
        deps = dag.get(node, set())
        if not deps:
            depth_cache[node] = 0
            return 0
        max_dep_depth = max(get_depth(d) for d in deps)
        depth_cache[node] = max_dep_depth + 1
        return depth_cache[node]

    for node in dag:
        get_depth(node)

    # 按深度分组
    groups: Dict[int, List[str]] = {}
    for node, depth in depth_cache.items():
        if depth not in groups:
            groups[depth] = []
        groups[depth].append(node)

    # 按深度排序返回
    return [groups[d] for d in sorted(groups.keys())]


def build_execution_plan(steps: List[dict]) -> List[List[str]]:
    """
    一步到位：从步骤列表生成并行执行计划。

    Args:
        steps: 工作流步骤列表

    Returns:
        List[List[str]]: 按层级分组的步骤 ID 列表
        如 [["step_1"], ["step_2", "step_3"], ["step_4"]]

    Raises:
        MissingDependencyError: 依赖不存在
        CycleDetectedError: 循环依赖
    """
    dag = build_dag(steps)
    cycle = detect_cycle(dag)
    if cycle:
        raise CycleDetectedError(cycle)
    return get_parallel_groups(dag)


def _get_step_by_id(steps: List[dict], step_id: str) -> dict | None:
    """根据 ID 查找步骤"""
    for s in steps:
        if s["id"] == step_id:
            return s
    return None


def get_dependent_steps(steps: List[dict], failed_step_id: str) -> List[str]:
    """
    当某步骤失败时，找出所有依赖它的步骤（这些步骤也应该被跳过）。

    Args:
        steps: 步骤列表
        failed_step_id: 失败的步骤 ID

    Returns:
        List[str]: 需要跳过的步骤 ID 列表
    """
    # 构建反向依赖图
    reverse: Dict[str, Set[str]] = {}
    for s in steps:
        for dep in s.get("depends_on", []):
            if dep not in reverse:
                reverse[dep] = set()
            reverse[dep].add(s["id"])

    # BFS 找出所有传递依赖
    to_skip = set()
    queue = deque([failed_step_id])
    while queue:
        node = queue.popleft()
        if node in reverse:
            for dep in reverse[node]:
                if dep not in to_skip:
                    to_skip.add(dep)
                    queue.append(dep)

    return list(to_skip)