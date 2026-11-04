"""Export only invented WP2A values. Never opens a HA/legacy/SQLite source."""
from pathlib import Path
import json
import math
from packages.contracts import Action, ReceiptStage, TimeWindow
from packages.offline.contracts import StatusView, APIReceipt, ForecastRecord, BudgetReceipt
from packages.planner import Curve
from packages.thermal import Interval
from packages.offline.codec import encode, decode


def content():
    now = 1793750400
    reference = now - 19 * 3600
    curve = Curve('synthetic.original.2026-11-03', reference - 45000,
                  tuple((reference + i * 3600,
                         Interval(round(21.2 + 0.4 * math.sin(i / 5), 6),
                                  round(21.2 + 0.4 * math.sin(i / 5), 6))) for i in range(25)),
                  'a' * 64, 3, 'synthetic.plan.frozen', (reference - 46000,))
    scope = TimeWindow(start=reference, end=reference+86400)
    records = {
        'original': ForecastRecord('synthetic.original.record', 'synthetic.cycle',
                                   'original', reference, curve, reference, 18.5, scope),
        'original_source': ForecastRecord('synthetic.original.source', 'synthetic.cycle',
                                          'latest', reference, curve, reference - 44000,
                                          18.5, scope),
        'budget': BudgetReceipt('synthetic.morning', 'synthetic.heat',18.5,8.2,1080,
                                 20.6,10.3,2.1,12,
                                 TimeWindow(start=now-3600,end=now+5*3600),now),
        'status': StatusView(1, 'synthetic.ui.boot', 7, None, Action.STOP,
                             'AUTO_HOLD', 'synthetic.ui.snapshot', 1793750400,
                             0, 0, None),
        'ack': StatusView(2, 'synthetic.ui.boot', 7, None, Action.HEAT,
                          'AUTO_PLAN', 'synthetic.ui.snapshot', 1793750400,
                          0, 0, ReceiptStage.ACKNOWLEDGED),
        'saved': APIReceipt('synthetic.ui.save', 'saved', 2, 2, 'simulated_readback'),
        'failed': APIReceipt('synthetic.ui.failed', 'unavailable', 1, None, 'simulated_io'),
    }
    for value in records.values():
        assert decode(encode(value)) == value
    return json.dumps({k: json.loads(encode(v)) for k, v in records.items()},
                      ensure_ascii=False, sort_keys=True, indent=2) + '\n'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[2] / 'frontend/src/contracts.fixture.json'
    if args.check:
        assert path.read_text() == content(), 'WP2A fixture drift'
    else:
        path.write_text(content())
