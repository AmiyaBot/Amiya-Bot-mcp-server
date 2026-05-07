{{- define "amiyabot-mcp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "amiyabot-mcp.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "amiyabot-mcp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "amiyabot-mcp.labels" -}}
helm.sh/chart: {{ include "amiyabot-mcp.chart" . }}
app.kubernetes.io/name: {{ include "amiyabot-mcp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ default "latest" .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "amiyabot-mcp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "amiyabot-mcp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "amiyabot-mcp.baseUrl" -}}
{{- required "values.config.baseUrl is required" .Values.config.baseUrl -}}
{{- end -}}

{{- define "amiyabot-mcp.image" -}}
{{- printf "%s:%s" .Values.image.repository (default "latest" .Values.image.tag) -}}
{{- end -}}

{{- define "amiyabot-mcp.ingressHost" -}}
{{- $baseUrl := include "amiyabot-mcp.baseUrl" . -}}
{{- $withoutScheme := regexReplaceAll "^https?://" $baseUrl "" -}}
{{- $hostPort := regexFind "^[^/]+" $withoutScheme -}}
{{- regexReplaceAll ":[0-9]+$" $hostPort "" -}}
{{- end -}}

{{- define "amiyabot-mcp.ingressPath" -}}
{{- $baseUrl := include "amiyabot-mcp.baseUrl" . -}}
{{- $withoutScheme := regexReplaceAll "^https?://" $baseUrl "" -}}
{{- $path := regexReplaceAll "^[^/]+" $withoutScheme "" -}}
{{- $normalized := trimSuffix "/" $path -}}
{{- if $normalized -}}
{{- $normalized -}}
{{- else -}}
/
{{- end -}}
{{- end -}}

{{- define "amiyabot-mcp.resourcesClaimName" -}}
{{- if .Values.persistence.existingClaim -}}
{{- .Values.persistence.existingClaim -}}
{{- else -}}
{{- printf "%s-resources" (include "amiyabot-mcp.fullname" .) -}}
{{- end -}}
{{- end -}}