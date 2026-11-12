import QtQuick
import Quickshell
import qs.Commons as Commons
import qs.Ui
import "PulseModel.js" as PulseModel

// Bar label showing today's keyboard and mouse activity from the local
// ActivityWatch, plus a popup with the breakdown. Counts only — the
// pulse-watcher never records key content (see the privacy invariant in
// AGENTS.md).
//
// Left click toggles the summary panel, right click forces a refresh.
BarWidget {
  id: root
  moduleName: "maxsh.pulse"

  property var today: null
  property string lastError: ""

  readonly property string awUrl: setting("awUrl", PulseModel.DEFAULT_AW_URL)

  // Reactive on today and on the translation catalog, so a late-loading
  // catalog still renders instead of leaving a raw key in the bar.
  readonly property string displayText: lastError !== ""
    ? "\uF109 —"
    : today
      ? "\uF109 " + PulseModel.compactNumber(today.presses)
        + "  \uF245 " + PulseModel.compactNumber(today.clicks)
      : ""

  readonly property string tooltipText: lastError !== ""
    ? (lastError === "noInputBucket"
        ? strings.t("pulse.error.noInputBucket")
        : strings.t("pulse.error.unreachable").arg(awUrl))
    : today
      ? strings.tn("pulse.presses", today.presses).arg(Commons.I18n.formatNumber(today.presses))
        + " · "
        + strings.tn("pulse.clicks", today.clicks).arg(Commons.I18n.formatNumber(today.clicks))
      : ""

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

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

  readonly property real openPanelIndicatorWidth: button.labelWidth
  readonly property real openPanelIndicatorHeight: Math.max(Commons.Style.space(10), Math.round(Commons.Style.bar.iconSlot * 0.55))

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
      root.today = result.today
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
    text: root.displayText
    hasVisualContent: text !== ""
    tooltipText: root.tooltipText
    // Activity counts to read, not a control to press: clicks open the panel
    // (the panel opening is the feedback), so the button itself never shrinks.
    pressFeedbackButtons: Qt.NoButton

    onPressed: function(button) {
      if (button === Qt.RightButton) root.refresh()
      else root.togglePanel()
    }
  }
}
