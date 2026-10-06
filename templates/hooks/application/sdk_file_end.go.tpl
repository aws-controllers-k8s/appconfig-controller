
// syncTags keeps the resource's tags in sync by calling TagResource and
// UntagResource based on the difference between desired and latest tags.
func (rm *resourceManager) syncTags(
	ctx context.Context,
	desired *resource,
	latest *resource,
) (err error) {
	rlog := ackrtlog.FromContext(ctx)
	exit := rlog.Trace("rm.syncTags")
	defer func() { exit(err) }()

	arn := string(*latest.ko.Status.ACKResourceMetadata.ARN)

	desiredTags := desired.ko.Spec.Tags
	latestTags := latest.ko.Spec.Tags

	added, removed := computeTagsDelta(desiredTags, latestTags)

	if len(removed) > 0 {
		_, err = rm.sdkapi.UntagResource(ctx, &svcsdk.UntagResourceInput{
			ResourceArn: &arn,
			TagKeys:     removed,
		})
		rm.metrics.RecordAPICall("UPDATE", "UntagResource", err)
		if err != nil {
			return err
		}
	}

	if len(added) > 0 {
		_, err = rm.sdkapi.TagResource(ctx, &svcsdk.TagResourceInput{
			ResourceArn: &arn,
			Tags:        added,
		})
		rm.metrics.RecordAPICall("UPDATE", "TagResource", err)
		if err != nil {
			return err
		}
	}

	return nil
}

// computeTagsDelta compares two tag maps and returns the tags to add/update
// and the tag keys to remove.
func computeTagsDelta(
	desired map[string]*string,
	latest map[string]*string,
) (added map[string]string, removed []string) {
	added = map[string]string{}
	removed = []string{}

	for k, v := range desired {
		latestVal, exists := latest[k]
		if !exists || aws.ToString(v) != aws.ToString(latestVal) {
			added[k] = aws.ToString(v)
		}
	}

	for k := range latest {
		if _, exists := desired[k]; !exists {
			removed = append(removed, k)
		}
	}

	return added, removed
}
