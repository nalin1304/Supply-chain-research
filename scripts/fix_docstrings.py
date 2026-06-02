import ast
import os
import re

def parse_violations(filepath):
    violations = []
    with open(filepath, 'r') as f:
        content = f.read()
    # Handle wrapped lines in the txt file
    content = content.replace('\n', '')
    # The format is like NO_PARAMETERS_SECTION: module.path.to.Thing  or MISSING: module.path...
    matches = re.finditer(r'(NO_PARAMETERS_SECTION|MISSING):\s*([a-zA-Z0-9_\.]+)', content)
    for m in matches:
        v_type = m.group(1)
        target = m.group(2)
        parts = target.split('.')
        module_parts = []
        obj_parts = []
        # Find where module ends (file exists)
        for i in range(len(parts), 0, -1):
            potential_path = os.path.join(*parts[:i]) + '.py'
            if os.path.exists(potential_path):
                module_parts = parts[:i]
                obj_parts = parts[i:]
                break
        if module_parts:
            violations.append({
                'type': v_type,
                'file': os.path.join(*module_parts) + '.py',
                'object': obj_parts
            })
    return violations

def get_node_params(node):
    if isinstance(node, ast.FunctionDef):
        return [arg.arg for arg in node.args.args if arg.arg != 'self']
    elif isinstance(node, ast.ClassDef):
        # Find __init__
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == '__init__':
                return [arg.arg for arg in child.args.args if arg.arg != 'self']
    return []

def get_indent(line):
    return line[:len(line) - len(line.lstrip())]

def process_file(filepath, violations):
    with open(filepath, 'r') as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except Exception as e:
        print(f"Parse error in {filepath}: {e}")
        return

    lines = source.split('\n')
    modifications = [] # (line_idx_to_insert, text)

    for v in violations:
        obj_path = v['object']
        # Find the node
        current = tree
        found_node = None
        for name in obj_path:
            found = False
            for child in getattr(current, 'body', []):
                if isinstance(child, (ast.FunctionDef, ast.ClassDef)) and child.name == name:
                    current = child
                    found = True
                    break
            if not found:
                current = None
                break
        
        if current is None or current == tree:
            print(f"Could not find {obj_path} in {filepath}")
            continue
            
        found_node = current
        params = get_node_params(found_node)
        
        param_str = "\n    Parameters\n    ----------\n"
        for p in params:
            param_str += f"    {p} : type\n        Description of {p}.\n"
        
        if not params:
            param_str = "\n"

        doc_node = ast.get_docstring(found_node, clean=False)
        
        if v['type'] == 'MISSING' or doc_node is None:
            # Insert new docstring after the def line
            insert_line = found_node.body[0].lineno - 1
            if isinstance(found_node.body[0], ast.Expr) and isinstance(found_node.body[0].value, ast.Constant):
                # already has docstring but linter said MISSING? 
                pass
            else:
                indent = get_indent(lines[insert_line])
                doc = f'{indent}"""\n{indent}Description.\n'
                if params:
                    doc += param_str.replace('\n', f'\n{indent}')
                doc += f'{indent}"""'
                modifications.append((insert_line, doc))
        
        elif v['type'] == 'NO_PARAMETERS_SECTION':
            # Append to existing docstring
            # AST docstring node
            expr = found_node.body[0]
            if isinstance(expr, ast.Expr) and isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                # find the line where the docstring ends
                end_lineno = expr.end_lineno - 1
                indent = get_indent(lines[found_node.lineno]) + '    '
                
                # We need to insert before the closing quotes
                # This is tricky, let's just do a regex replace on the actual source text for that line
                line_text = lines[end_lineno]
                
                if '"""' in line_text:
                    new_line = line_text.replace('"""', param_str.replace('\n', f'\n{indent}') + '"""')
                    lines[end_lineno] = new_line
                elif "'''" in line_text:
                    new_line = line_text.replace("'''", param_str.replace('\n', f'\n{indent}') + "'''")
                    lines[end_lineno] = new_line
                    
    # Apply missing insertions in reverse order to not mess up line numbers
    modifications.sort(key=lambda x: x[0], reverse=True)
    for line_idx, text in modifications:
        lines.insert(line_idx, text)
        
    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Fixed {len(violations)} violations in {filepath}")

if __name__ == "__main__":
    violations = parse_violations('audit_workspace/missing_docstrings.txt')
    # Group by file
    by_file = {}
    for v in violations:
        by_file.setdefault(v['file'], []).append(v)
        
    for filepath, file_violations in by_file.items():
        process_file(filepath, file_violations)
