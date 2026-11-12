import QtQuick
import Quickshell
import qs.Commons as Commons
import qs.Ui
import "PulseModel.js" as PulseModel

// Bar widget showing today's input split — keyboard vs mouse vs idle — as a
// small stacked bar: three proportional segments in one accent color at
// three intensities, so it reads correctly on any theme. The popup shows
// the exact percentages. Absolute counts are deliberately not displayed;
// relative values only (product goal), and the pulse-watcher never records
// key content anyway (privacy invariant in AGENTS.md).
//
// Left click toggles the summary panel, right click forces a refresh.
// Horizontal bar only for now; vertical bars fall back to the same row.
BarWidget {
  id: root
  moduleName: "maxsh.pulse"

  property var activity: null
  property string lastError: ""

  readonly property string awUrl: setting("awUrl", PulseModel.DEFAULT_AW_URL)
  readonly property bool hasData: activity !== null && activity.spanMinutes > 0

  // One hue, three intensities: keyboard bright, mouse mid, idle dim.
  readonly property color kbColor: Commons.Color.accent
  readonly property color mouseColor: Commons.Util.alpha(Commons.Color.accent, 0.45)
  readonly property color idleColor: Commons.Util.alpha(Commons.Color.accent, 0.15)

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  // Reactive on activity and on the translation catalog, so a late-loading
  // catalog still renders instead of leaving a raw key in the tooltip.
  readonly property string tooltipText: lastError !== ""
    ? (lastError === "noInputBucket"
        ? strings.t("pulse.error.noInputBucket")
        : strings.t("pulse.error.unreachable").arg(awUrl))
    : !hasData
      ? strings.t("pulse.noData")
      : strings.t("pulse.keyboard") + " " + Commons.I18n.formatNumber(activity.kbPct) + "% · "
        + strings.t("pulse.mouse") + " " + Commons.I18n.formatNumber(activity.mousePct) + "% · "
        + strings.t("pulse.idle") + " " + Commons.I18n.formatNumber(activity.idlePct) + "%"

  // ---- Summary popup. Shape contract for shell summon/hide/toggle routing:
  //      Bar.findPanelWidget requires open/close/opened on the bar-widget root.
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function togglePanel() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  // Forwarded so this widget can stand in for the panel as the bar's popout
  // identity: Bar.requestPopout prefers closeForPopoutSwitch over close.
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  // The widget paints a fixed-width row, so the open-panel indicator dot
  // takes the row's width rather than a rule across the whole slot.
  readonly property real openPanelIndicatorWidth: Style.space(48)
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Component.onCompleted: root.refresh()

  Timer {
    interval: Math.max(5, Number(root.setting("pollSeconds", 60)) || 60) * 1000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  function refresh() {
    PulseModel.fetchToday(root.awUrl, function(result) {
      if (!result.ok) {
        root.lastError = result.error
        return
      }
      root.lastError = ""
      root.activity = result.activity
    })
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: ""
    labelVisible: false
    hasVisualContent: true
    fixedWidth: Style.space(64)
    tooltipText: root.tooltipText
    // A proportion to read at a glance, not a control to press: clicks open
    // the panel (the panel opening is the feedback), so the button itself
    // never shrinks.
    pressFeedbackButtons: Qt.NoButton

    onPressed: function(button) {
      if (button === Qt.RightButton) root.refresh()
      else root.togglePanel()
    }

    // The stacked split: idle fills the whole pill dimly; keyboard and mouse
    // stack over it from the left, so the empty tail reads as idle time.
    Item {
      width: Style.space(48)
      height: Style.space(10)
      anchors.centerIn: parent

      readonly property real unit: root.hasData ? width / 100.0 : 0

      Rectangle {
        anchors.fill: parent
        radius: Style.space(2)
        color: root.idleColor
      }

      Rectangle {
        id: kbSegment
        x: 0
        width: parent.unit * (root.hasData ? root.activity.kbPct : 0)
        height: parent.height
        radius: Style.space(2)
        color: root.kbColor
      }

      Rectangle {
        id: mouseSegment
        x: kbSegment.width
        width: parent.unit * (root.hasData ? root.activity.mousePct : 0)
        height: parent.height
        radius: Style.space(2)
        color: root.mouseColor
      }
    }
  }
}
