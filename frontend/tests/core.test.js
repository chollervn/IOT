import test from 'node:test';
import assert from 'node:assert/strict';
import { slotState, countSlots, sampleSummary, durationSummary, timestamp, dateTime, timeRange, query, esc } from '../assets/core.js';
import { renderPage } from '../assets/views.js';
import { driverSummary, viewerShell, viewerContent } from '../assets/viewer.js';

const at = Date.parse('2026-10-26T08:00:00Z');
const device = { id: 1, status: 'active', connectivity: 'online', effective_offline_timeout_s: 30 };
const slot = { device_id: 1, updated_at: '2026-10-26T07:59:40Z', fresh: true, occupied: false };

test('an old free sample is never shown as a currently available space', () => {
  assert.equal(slotState(slot, [device], true, at), 'free');
  assert.equal(slotState(slot, [device], true, at + 10000), 'unknown');
  assert.equal(slotState(slot, [device], false, at), 'unknown');
  assert.equal(slotState({ ...slot, fresh: false }, [device], true, at), 'unknown');
  assert.equal(slotState(slot, [{ ...device, status: 'maintenance' }], true, at), 'unknown');
  assert.equal(slotState(slot, [{ ...device, connectivity: 'offline' }], true, at), 'unknown');
});

test('a lost API connection changes both visible spaces to unknown', () => {
  const result = countSlots([slot, { ...slot, occupied: true }], [device], false, at);
  assert.deepEqual(result, { capacity: 2, free: 0, occupied: 0, unknown: 2 });
});

test('percentages are weighted by samples rather than averaging hourly percentages', () => {
  assert.deepEqual(sampleSummary({ buckets: [
    { slot: 'P1', samples: 1, occupied_samples: 1 }, { slot: 'P1', samples: 9, occupied_samples: 1 },
  ] }), [{ slot: 'P1', samples: 10, occupied: 2, percent: 20 }]);
});

test('filters convert the displayed UTC+7 time correctly and reject inverted ranges', () => {
  assert.deepEqual(timeRange('2026-10-26T00:00', '2026-10-26T07:00'), {
    from_at: '2026-10-25T17:00:00.000Z', to_at: '2026-10-26T00:00:00.000Z',
  });
  assert.throws(() => timeRange('2026-10-27T12:00', '2026-10-26T12:00'));
  assert.equal(timestamp('2026-10-26T08:00:00'), at);
  assert.match(dateTime('2026-10-26T00:00:00Z', true), /07:00:00/);
});

test('history query encoding preserves timezone signs and excludes unset filters', () => {
  const encoded = query({ device_id: 'esp32_01', from_at: '2026-10-26T08:00:00+07:00', to_at: undefined });
  const decoded = new URLSearchParams(encoded);
  assert.equal(decoded.get('from_at'), '2026-10-26T08:00:00+07:00');
  assert.equal(decoded.has('to_at'), false);
});

test('untrusted labels are escaped and direct admin routes stay hidden for viewer', () => {
  assert.equal(esc('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  const html = renderPage({ me: { role: 'viewer' }, route: { page: 'users' } });
  assert.match(html, /NHÀ XE CỦA BẠN/);
  assert.doesNotMatch(html, /data-action="create-device"/);
  assert.doesNotMatch(html, /data-action="create-user"/);
});

test('driver counts use freshness and never treat unknown spaces as a full car park', () => {
  const parking = { slots: [
    { name: 'P1', status: 'available', updated_at: '2026-10-26T07:59:59Z', valid_until: '2026-10-26T08:00:10Z' },
    { name: 'P2', status: 'occupied', updated_at: '2026-10-26T07:59:59Z', valid_until: '2026-10-26T08:00:10Z' },
  ] };
  assert.equal(driverSummary(parking, true, at).available, 1);
  assert.equal(driverSummary(parking, true, at + 10000).unknown, 2);
  assert.equal(driverSummary(parking, false, at).available, 0);
  assert.equal(driverSummary(parking, true, at - 2000).unknown, 2);
  const html = viewerContent({ me: { role: 'viewer' }, parking, apiConnected: false });
  assert.match(html, /Đang kiểm tra chỗ đỗ/);
  assert.doesNotMatch(html, /Nhà xe hiện đã đầy/);
});

test('the driver navigation and parking screen omit technical administration', () => {
  const s = { me: { role: 'viewer', username: '<driver>' }, route: { page: 'overview' }, parking: null, apiConnected: true };
  const html = viewerShell(s) + viewerContent(s);
  assert.match(html, /&lt;driver&gt;/);
  for (const word of ['#/devices', '#/telemetry', '#/commands', '#/alerts', '#/users', 'GPIO', 'MQTT', 'firmware']) {
    assert.ok(!html.includes(word), word);
  }
});

test('duration percentages exclude unknown time and combine by seconds', () => {
  const rows = durationSummary({ buckets: [
    { slot: 'P1', occupied_seconds: 5, available_seconds: 5, unknown_seconds: 50 },
    { slot: 'P1', occupied_seconds: 15, available_seconds: 75, unknown_seconds: 0 },
    { slot: 'P2', occupied_seconds: 0, available_seconds: 0, unknown_seconds: 100 },
  ] });
  assert.equal(rows[0].percent, 20);
  assert.equal(rows[0].observed, 100);
  assert.equal(rows[0].unknown, 50);
  assert.equal(rows[1].percent, null);
});
