"""Safe YAML loading that refuses silently overwritten execution fields."""
import yaml


class ExecutionLoader(yaml.SafeLoader):
    """Reject duplicate explicit keys, retaining YAML aliases and merge defaults."""

    def __init__(self, stream):
        super().__init__(stream)
        self._checked_mappings = set()

    def flatten_mapping(self, node):
        # Check before PyYAML expands merges: explicit overrides of defaults are
        # valid, while repeated keys in the original mapping are ambiguous.
        if node not in self._checked_mappings:
            self._checked_mappings.add(node)
            keys = set()
            for key_node, _ in node.value:
                key = "<<" if key_node.tag == "tag:yaml.org,2002:merge" else self.construct_object(key_node)
                try:
                    duplicate = key in keys
                    keys.add(key)
                except TypeError as exc:
                    raise yaml.constructor.ConstructorError(
                        None, None, "YAML fields must be scalar keys", key_node.start_mark,
                    ) from exc
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        None, None, "Duplicate YAML field", key_node.start_mark,
                    )
        super().flatten_mapping(node)
