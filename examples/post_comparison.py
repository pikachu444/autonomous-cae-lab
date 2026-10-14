"""Public manufactured fields, no solver. Standard-library fixture writer."""
from copy import deepcopy
import json
from pathlib import Path
from xml.sax.saxutils import escape


def array(name, values, components=1, dtype='Float64'):
    flat = [value for row in values for value in (row if isinstance(row, (list,tuple)) else [row])]
    return '<DataArray type="' + dtype + '" Name="' + escape(name) + '" NumberOfComponents="' + str(components) + '" format="ascii">' + ' '.join(str(v) for v in flat) + '</DataArray>'


def write_grid(path, points, force, stress):
    points_data = array('Points', points, 3)
    fields = array('force', [force]*4, 3) + array('pressure', [stress]*4)
    fields += array('NativeNodeId', [101,102,103,104], dtype='Int64')
    fields += array('quality', [1,1,0,1], dtype='Int64')
    cells = array('connectivity',[0,1,2,3],dtype='Int64')+array('offsets',[4],dtype='Int64')+array('types',[10],dtype='UInt8')
    xml = '<?xml version="1.0"?><VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian"><UnstructuredGrid><Piece NumberOfPoints="4" NumberOfCells="1"><Points>' + points_data + '</Points><Cells>' + cells + '</Cells><PointData>' + fields + '</PointData><CellData/></Piece></UnstructuredGrid></VTKFile>'
    path.write_text(xml,encoding='utf-8')


def create(folder):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    points=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
    bpoints=[[y/1000,-x/1000,z/1000] for x,y,z in points]
    write_grid(folder/'a.vtu',points,[0,2,0],2.)
    write_grid(folder/'b0.vtu',bpoints,[.001,0,0],2e6)
    write_grid(folder/'b1.vtu',bpoints,[.003,0,0],2e6)
    for name,frames in [('a',[(.5,'a.vtu')]),('b',[(0.,'b0.vtu'),(1.,'b1.vtu')])]:
        (folder/(name+'.pvd')).write_text('<?xml version="1.0"?><VTKFile type="Collection" version="0.1" byte_order="LittleEndian"><Collection>'+
            ''.join('<DataSet timestep="'+str(time)+'" group="" part="0" file="'+file+'"/>' for time,file in frames)+
            '</Collection></VTKFile>',encoding='utf-8')
    side={'source_ref':'result','array':'force','association':'POINTS','quantity':'force','units':'N',
        'measure':'force','frame':'global','coordinate_units':'mm','coordinate_frame':'global',
        'layout':{'kind':'vector','components':['x','y','z']},'time':.5,'time_units':'s','time_origin':'physical_time',
        'sampling':{'mode':'exact','time':.5},'clock_offset':0.,'validity_masks':['quality']}
    recipe={'version':2,'a':side,'b':deepcopy(side),'method':'same_mesh','tolerance':0.,
        'target':{'units':'N'},'selection':'y','difference':'selected_difference','percent':'relative_a',
        'clock':{'value':.5,'unit':'s','semantics':'physical_time'},
        'alignment':{'geometry_rotation':[[0,-1,0],[1,0,0],[0,0,1]],'response_rotation':[[0,-1,0],[1,0,0],[0,0,1]],
                     'translation':[0,0,0],'geometry_declared':True,'response_declared':True}}
    recipe['b'].update(source_ref='replace-with-added-source', units='kN',frame='rotated',coordinate_units='m',coordinate_frame='rotated',
        sampling={'mode':'linear','bracket':[0.,1.],'max_gap':1.},time=None)
    (folder/'comparison.json').write_text(json.dumps(recipe,ensure_ascii=False,indent=2),encoding='utf-8')
    return recipe


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    args=parser.parse_args(); create(args.directory)
    print(args.directory)
