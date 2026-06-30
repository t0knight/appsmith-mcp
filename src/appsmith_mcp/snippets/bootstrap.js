(() => {
  if (window.__store) return true;
  const root = document.getElementById('root');
  if (!root) return false;
  const k = Object.keys(root).find(k => k.startsWith('__reactContainer'));
  if (!k) return false;
  const seen = new Set();
  function walk(n, d) {
    if (!n || seen.has(n) || d > 50) return null;
    seen.add(n);
    if (n.stateNode?.store?.dispatch) return n.stateNode.store;
    if (n.memoizedProps?.store?.dispatch) return n.memoizedProps.store;
    if (n.memoizedState?.store?.dispatch) return n.memoizedState.store;
    return walk(n.child, d+1) || walk(n.sibling, d+1);
  }
  window.__store = walk(root[k], 0);
  return !!window.__store;
})()
