"""Scoped presentation for the existing legacy coefficient table.

Root attaches this to the shared Numerical window; raw cell/owner values remain
unchanged. Mixed Request Plans use their explicit free/fixed/dependent editor.
"""
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtWidgets import QApplication,QStyle,QStyledItemDelegate,QStyleOptionButton,QStyleOptionViewItem


class FreeCoefficientDelegate(QStyledItemDelegate):
    def _box(self,option):
        style=option.widget.style() if option.widget else QApplication.style()
        size=style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth,widget=option.widget)
        return QRect(option.rect.center().x()-size//2,option.rect.center().y()-size//2,size,size)

    def paint(self,painter,option,index):
        value=index.data(Qt.ItemDataRole.DisplayRole)
        if value not in ('true','false'):return super().paint(painter,option,index)
        painter.save()
        style=option.widget.style() if option.widget else QApplication.style()
        background=QStyleOptionViewItem(option);self.initStyleOption(background,index);background.text=''
        background.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,background,painter,option.widget)
        checkbox=QStyleOptionButton();checkbox.rect=self._box(option)
        checkbox.state=(QStyle.StateFlag.State_Enabled if index.flags() & Qt.ItemFlag.ItemIsEditable else QStyle.StateFlag.State_None)
        checkbox.state|=QStyle.StateFlag.State_On if value=='true' else QStyle.StateFlag.State_Off
        style.drawControl(QStyle.ControlElement.CE_CheckBox,checkbox,painter,option.widget);painter.restore()

    def createEditor(self,parent,option,index):
        if index.data(Qt.ItemDataRole.DisplayRole) in ('true','false'):return None
        return super().createEditor(parent,option,index)

    def editorEvent(self,event,model,option,index):
        if not index.flags() & Qt.ItemFlag.ItemIsEditable or index.data() not in ('true','false'):return False
        toggle=(event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Space or
            event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton and self._box(option).contains(event.position().toPoint()))
        if toggle:return model.setData(index,'false' if index.data()=='true' else 'true',Qt.ItemDataRole.EditRole)
        return False


class VariableNameDisplay(QStyledItemDelegate):
    def __init__(self,labels,parent=None):super().__init__(parent);self.labels=dict(labels)
    def displayText(self,value,locale):return self.labels.get(str(value),str(value))


def refresh_coefficient_display(window,*,descriptors=None,model_label=None):
    """Use actual labels supplied by the frozen model; never changes item text."""
    table=window.variables
    labels={item['id']:item.get('label',item['id']) for item in descriptors or []}
    if hasattr(window, 'variable_editor'):
        window.variable_editor.set_variable_labels(labels)
        table.verticalHeader().setVisible(False)
        for column,width in enumerate((110,45,66,66,66,56,56)):table.setColumnWidth(column,width)
        if model_label is not None:
            settings=(window._material or {}).get('draft',{}).get('settings',{})
            window.material_label.setText(model_label+' ['+str(settings.get('stress_unit',''))+']')
        return
    if not hasattr(window,'_free_coefficient_display'):window._free_coefficient_display=FreeCoefficientDelegate(table)
    if not hasattr(window,'_variable_name_display'):window._variable_name_display=VariableNameDisplay(labels,table)
    else:window._variable_name_display.labels=labels
    table.setItemDelegateForColumn(5,window._free_coefficient_display)
    table.setItemDelegateForColumn(0,window._variable_name_display)
    if not hasattr(window,'_coordinate_display'):
        window._coordinate_display=VariableNameDisplay({'linear':'선형','log':'로그'},table)
    table.setItemDelegateForColumn(6,window._coordinate_display)
    if not hasattr(window,'_coefficient_checkbox_sync'):
        def sync(item):
            if item.column()!=5:return
            blocked=table.blockSignals(True)
            try:
                if item.text() in ('true','false'):
                    item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if item.text()=='true' else Qt.CheckState.Unchecked)
                    item.setData(Qt.ItemDataRole.AccessibleTextRole,'탐색 변수' if item.text()=='true' else '고정 변수')
                else:
                    item.setData(Qt.ItemDataRole.CheckStateRole,None)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            finally:table.blockSignals(blocked)
        window._coefficient_checkbox_sync=sync
        table.itemChanged.connect(sync)
    for row in range(table.rowCount()):
        item=table.item(row,5)
        if item is not None:window._coefficient_checkbox_sync(item)
    table.verticalHeader().setVisible(False)
    for column,width in enumerate((98,44,56,56,56,46,50)):table.setColumnWidth(column,width)
    if model_label is not None:
        settings=(window._material or {}).get('draft',{}).get('settings',{})
        window.material_label.setText(model_label+' ['+str(settings.get('stress_unit',''))+']')


def refresh_frozen_material_display(window):
    """Read the Plan's frozen material descriptor, never the live Material owner."""
    material=(window._material or {}).get('draft',{})
    if material.get('backend')!='material.felupe':return
    from caelab.adapters.felupe_material import FelupeMaterialAdapter
    settings=material.get('settings',{})
    try:descriptors=FelupeMaterialAdapter().describe_inputs(settings)
    except (ValueError,KeyError,TypeError):descriptors=[]
    # Same physical model names already used by Material's model selector.
    name={'linear_elastic':'선형 탄성','neo_hooke':'Neo-Hooke'}.get(settings.get('model'))
    refresh_coefficient_display(window,descriptors=descriptors,model_label=name)
