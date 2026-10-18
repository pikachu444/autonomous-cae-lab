"""Authored synthetic 1 mm cube for the bounded Case A acceptance, not a mesher."""


def cube_c3d10():
    # Fixed positive-order corner tetrahedra around the (0,0,0)-(1,1,1) diagonal.
    xyz=[(0.,0.,0.),(1.,0.,0.),(1.,1.,0.),(0.,1.,0.),
         (0.,0.,1.),(1.,0.,1.),(1.,1.,1.),(0.,1.,1.)]
    tetra=[(0,1,2,6),(0,2,3,6),(0,3,7,6),(0,7,4,6),(0,4,5,6),(0,5,1,6)]
    mids={};cells=[]
    for corners in tetra:
        cell=[i+1 for i in corners]
        for a,b in ((0,1),(1,2),(0,2),(0,3),(1,3),(2,3)):
            edge=tuple(sorted((corners[a],corners[b])))
            if edge not in mids:
                xyz.append(tuple((xyz[edge[0]][j]+xyz[edge[1]][j])/2 for j in range(3)))
                mids[edge]=len(xyz)
            cell.append(mids[edge])
        cells.append(cell)
    return {'points_mm':[list(p) for p in xyz], 'cells_C3D10_1_based':cells,
            'origin':'authored_synthetic_fixture_not_existing_native_execution',
            'length_unit':'mm','geometry':'1 mm axis-aligned cube',
            'roi':'whole homogeneous box; distinct node/IP identities from DP Hex8',
            'gauge':'mean ux(x=1) minus mean ux(x=0), divided by original 1 mm length'}
