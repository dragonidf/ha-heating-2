import ast
import json
from pathlib import Path
import unittest

ROOT = Path('ha_sdk/heating_ai')

class NativeBoundaryTests(unittest.TestCase):
    def test_no_service_or_external_transport_code(self):
        for path in [*ROOT.glob('*.py'), *Path('packages/ha_native').glob('*.py')]:
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertTrue(all(n.name.split('.')[0] not in {'socket','requests','urllib','paho','tuya','subprocess'} for n in node.names),path)
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], {'socket','requests','urllib','paho','tuya','subprocess'}, path)
                if isinstance(node,ast.Attribute):
                    self.assertNotEqual(node.attr, 'services', str(path))
                if isinstance(node,ast.Call):
                    name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                    self.assertNotIn(name,{'async_call','call_service','publish','send_service','exec','eval','__import__'},str(path))
    def test_manifest_has_no_device_dependency(self):
        manifest=json.loads((ROOT/'manifest.json').read_text())
        self.assertTrue(manifest['config_flow'])
        self.assertEqual(manifest['requirements'],[])
        self.assertEqual(set(manifest['dependencies']),{'frontend','http','websocket_api','panel_custom'})
        self.assertTrue(manifest['single_config_entry'])
    def test_only_read_only_entities_are_packaged(self):
        self.assertEqual(sorted(p.name for p in ROOT.glob('*.py')),['__init__.py','config_flow.py','const.py','passive.py','sensor.py'])
        sensor=(ROOT/'sensor.py').read_text()
        self.assertIn('_attr_entity_registry_enabled_default = False',sensor)
        self.assertIn('"physical_verified": False',sensor)
    def test_native_panel_has_no_new_transport_or_token_storage(self):
        text='\n'.join(Path('frontend/src',name).read_text() for name in ['nativeAdapter.ts','panel.tsx'])
        for token in ['new WebSocket','fetch(', 'localStorage','sessionStorage','access_token','refresh_token','call_service']:
            self.assertNotIn(token,text)
