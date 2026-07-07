#!/usr/bin/env python3
"""
Memento-X 工作流 Schema 验证工具

用法：
    python3 validate.py schema/workflow.json docs/WORKFLOW_EXAMPLES.md
    或
    python3 validate.py schema/workflow.json < some_workflow.json

依赖：pip install jsonschema
"""
import json
import sys
import re
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("需要安装 jsonschema: pip install jsonschema")
    sys.exit(1)


def extract_workflows_from_md(filepath: str) -> list[dict]:
    """从 Markdown 文档中提取所有 JSON 工作流示例"""
    with open(filepath) as f:
        content = f.read()

    # 提取所有 ```json ... ``` 代码块
    blocks = re.findall(r'```json\n(.*?)```', content, re.DOTALL)
    workflows = []
    for block in blocks:
        try:
            wf = json.loads(block)
            if "version" in wf and "steps" in wf:
                workflows.append(wf)
        except json.JSONDecodeError:
            continue
    return workflows


def validate_workflow(schema: dict, workflow: dict, name: str) -> list[str]:
    """验证单个工作流，返回错误列表"""
    errors = []
    try:
        jsonschema.validate(workflow, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"  [{name}] Schema 验证失败: {e.message}")
        # 如果路径存在，指出具体位置
        if e.path:
            errors.append(f"    位置: {' -> '.join(str(p) for p in e.path)}")
    except jsonschema.SchemaError as e:
        errors.append(f"  [{name}] Schema 本身有误: {e.message}")
    return errors


def validate_dependencies(workflow: dict, name: str) -> list[str]:
    """验证依赖关系正确性"""
    errors = []
    step_ids = {s["id"] for s in workflow["steps"]}

    # 检查 depends_on 引用是否存在
    for step in workflow["steps"]:
        for dep in step.get("depends_on", []):
            if dep not in step_ids:
                errors.append(f"  [{name}] 步骤 '{step['id']}' 依赖了不存在的步骤 '{dep}'")

    # 检查是否有循环依赖
    for step in workflow["steps"]:
        visited = set()
        stack = [step["id"]]

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)

            # 找到当前步骤的所有依赖
            for s in workflow["steps"]:
                if s["id"] == current:
                    for dep in s.get("depends_on", []):
                        if dep == step["id"]:
                            errors.append(f"  [{name}] 检测到循环依赖: {step['id']} ↔ {current}")
                        stack.append(dep)
                    break

    return errors


def main():
    if len(sys.argv) < 2:
        print("用法: python3 validate.py <schema.json> [examples.md]")
        sys.exit(1)

    schema_path = sys.argv[1]

    # 加载 Schema
    with open(schema_path) as f:
        schema = json.load(f)

    # 验证 Schema 本身
    try:
        jsonschema.Draft7Validator.check_schema(schema)
        print("✅ JSON Schema 定义合法")
    except jsonschema.SchemaError as e:
        print(f"❌ Schema 定义有误: {e.message}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        # 从 Markdown 提取示例并验证
        examples_path = sys.argv[2]
        if not Path(examples_path).exists():
            print(f"❌ 文件不存在: {examples_path}")
            sys.exit(1)

        workflows = extract_workflows_from_md(examples_path)
        if not workflows:
            print(f"❌ 未在 {examples_path} 中找到 JSON 工作流示例")
            sys.exit(1)

        print(f"\n发现 {len(workflows)} 个工作流示例，开始验证...\n")

        all_ok = True
        for i, wf in enumerate(workflows):
            wf_id = wf.get("workflow_id", f"example_{i+1}")
            name = f"{wf_id} ({wf.get('understood', 'N/A')[:40]}...)"

            schema_errors = validate_workflow(schema, wf, name)
            dep_errors = validate_dependencies(wf, name)

            if not schema_errors and not dep_errors:
                print(f"✅ 示例 {i+1}: {name}")
            else:
                all_ok = False
                print(f"❌ 示例 {i+1}: {name}")
                for e in schema_errors + dep_errors:
                    print(e)

        # 统计
        total_steps = sum(len(wf["steps"]) for wf in workflows)
        all_actions = [s["action"] for wf in workflows for s in wf["steps"]]
        unique_actions = set(all_actions)

        print(f"\n{'='*50}")
        print(f"总计: {len(workflows)} 个工作流, {total_steps} 个步骤")
        print(f"涉及工具: {', '.join(sorted(unique_actions))}")
        if all_ok:
            print("✅ 全部验证通过")
        else:
            print("❌ 存在验证失败的示例")
            sys.exit(1)
    else:
        # 从 stdin 读取
        wf = json.load(sys.stdin)
        name = wf.get("workflow_id", "stdin")
        schema_errors = validate_workflow(schema, wf, name)
        dep_errors = validate_dependencies(wf, name)

        if not schema_errors and not dep_errors:
            print(f"✅ 工作流 {name} 验证通过")
        else:
            for e in schema_errors + dep_errors:
                print(e)
            sys.exit(1)


if __name__ == "__main__":
    main()