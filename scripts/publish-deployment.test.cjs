const assert = require('node:assert/strict');
const {test} = require('node:test');
const publish = require('./publish-deployment.cjs');

function setup({main = ['tested', 'tested'], previous, previousTree, failure} = {}) {
  const calls = [];
  let mainReads = 0;
  const git = {
    async getRef({ref}) {
      if (ref === 'heads/main') return {data: {object: {sha: main[mainReads++]}}};
      if (failure) throw Object.assign(new Error('Denied'), {status: failure});
      if (!previous) throw Object.assign(new Error('Absent'), {status: 404});
      return {data: {object: {sha: previous}}};
    },
    async getCommit() { return {data: {tree: {sha: previousTree}}}; },
    async createTree(arg) { calls.push(['tree', arg]); return {data: {sha: 'new-tree'}}; },
    async createCommit(arg) { calls.push(['commit', arg]); return {data: {sha: 'new-commit'}}; },
    async updateRef(arg) { calls.push(['update', arg]); },
    async createRef(arg) { calls.push(['create', arg]); },
  };
  const run = () => publish({
    github: {rest: {git}},
    context: {repo: {owner: 'Owner', repo: 'Repo'}, sha: 'tested'},
    core: {info() {}},
  });
  return {run, calls};
}

test('first deployment contains only the pinned Compose file', async () => {
  const {run, calls} = setup();
  await run();
  const tree = calls.find(([name]) => name === 'tree')[1].tree;
  assert.equal(tree.length, 1);
  assert.equal(tree[0].path, 'compose.yaml');
  assert.match(tree[0].content, /image: ghcr.io\/owner\/repo:tested/);
  assert.ok(!tree[0].content.includes('${RSA_IMAGE'));
  assert.deepEqual(calls.find(([name]) => name === 'commit')[1].parents, []);
  assert.equal(calls.at(-1)[1].ref, 'refs/heads/deploy/production');
});

test('existing deployment advances without force and retains history', async () => {
  const {run, calls} = setup({previous: 'old-commit'});
  await run();
  assert.deepEqual(calls.find(([name]) => name === 'commit')[1].parents, ['old-commit']);
  assert.equal(calls.at(-1)[0], 'update');
  assert.equal(calls.at(-1)[1].force, false);
});

test('stale builds and repeated publications do not update the branch', async () => {
  for (const options of [
    {main: ['newer']},
    {main: ['tested', 'newer']},
    {previous: 'old-commit', previousTree: 'new-tree'},
  ]) {
    const {run, calls} = setup(options);
    await run();
    assert.ok(!calls.some(([name]) => ['update', 'create'].includes(name)));
  }
});

test('authorization failures are not treated as a missing deployment branch', async () => {
  const {run, calls} = setup({failure: 403});
  await assert.rejects(run(), /Denied/);
  assert.deepEqual(calls, []);
});
